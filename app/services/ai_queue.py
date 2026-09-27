"""Bounded background queue for AI analysis.

Why this exists
---------------
Before this module, ``_save_posts()`` called ``auto_analyze_posts()``
*synchronously* from inside ``run_scraping_cycle()``, which is awaited by an
``async def`` endpoint. That reached ``run_sync()``, which detected the running
loop and blocked it on ``ThreadPoolExecutor(...).result()`` for the whole batch.

Measured on this codebase: a 20-post batch froze the server for 30.3s of 30.3s
(100%). ``GET /health`` -- the cheapest endpoint in the app -- took 30,229 ms
and only 9 requests completed where ~600 were expected. At the shipped defaults
(``batch_size=50``, ``ai_max_concurrency=1``, ``ai_request_timeout=180``) a
realistic local model means a ~6.7 minute total outage per batch, and a stalled
provider means 2.5 hours.

Design
------
* A bounded ``asyncio.Queue``. Ingestion never blocks on analysis, and a spike
  degrades instead of exhausting memory: when the queue is full the post simply
  stays ``ai_status='pending'`` in the database and the next cycle claims it.
* The worker owns its own ``Session`` and its own event loop task, started from
  the FastAPI lifespan. A stalled provider therefore cannot affect request
  handling at all.
* Batching with a short coalescing window. Scraping produces posts in bursts, so
  draining up to ``ai_queue_batch_size`` at once turns N provider round trips
  into N/batch_size while still keeping the queue responsive.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, Iterable

from config import settings

logger = logging.getLogger(__name__)


class AIAnalysisQueue:
    """Bounded FIFO of post IDs awaiting AI analysis."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[int] | None = None
        self._workers: list[asyncio.Task] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._maxsize = 0
        # Operator throttle. While paused the workers keep running but never
        # claim or process anything, so a frontend rebuild gets the whole
        # database and CPU budget.
        self._paused = bool(getattr(settings, "ai_queue_paused", False) or False)
        self._reclaim_task: asyncio.Task | None = None
        self.reclaimed = 0
        # Counters surfaced on /api/ai/status and the health endpoint.
        self.enqueued = 0
        self.processed = 0
        self.failed = 0
        self.dropped = 0

    # -- operator throttle ---------------------------------------------
    @property
    def is_paused(self) -> bool:
        return self._paused

    def pause(self) -> None:
        """Stop consuming work. Already-running batches are allowed to finish."""
        if not self._paused:
            self._paused = True
            logger.info("AI analysis queue paused by operator")

    def resume(self) -> None:
        """Resume consuming work."""
        if self._paused:
            self._paused = False
            logger.info("AI analysis queue resumed by operator")

    # -- lifecycle -----------------------------------------------------
    def start(self) -> None:
        """Bind the queue to the running loop and spawn worker task(s)."""
        self._loop = asyncio.get_running_loop()
        self._maxsize = max(1, int(getattr(settings, "ai_queue_maxsize", 1000) or 1000))
        self._queue = asyncio.Queue(maxsize=self._maxsize)
        worker_count = max(1, int(getattr(settings, "ai_queue_workers", 1) or 1))
        self._workers = [
            self._loop.create_task(self._worker(index), name=f"ai-analysis-{index}")
            for index in range(worker_count)
        ]
        if bool(getattr(settings, "ai_reclaim_enabled", True)):
            self._reclaim_task = self._loop.create_task(
                self._reclaim_loop(), name="ai-reclaim"
            )
        logger.info(
            "AI analysis queue started: workers=%d maxsize=%d batch=%d concurrency=%d "
            "paused=%s reclaim=%s/%ss",
            worker_count,
            self._maxsize,
            int(getattr(settings, "ai_queue_batch_size", 10) or 10),
            int(getattr(settings, "ai_max_concurrency", 5) or 5),
            self._paused,
            bool(getattr(settings, "ai_reclaim_enabled", True)),
            int(getattr(settings, "ai_reclaim_interval_seconds", 15) or 15),
        )

    async def stop(self) -> None:
        """Drain in-flight work and cancel the workers."""
        if self._reclaim_task is not None:
            self._reclaim_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reclaim_task
            self._reclaim_task = None
        for task in self._workers:
            task.cancel()
        for task in self._workers:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._workers.clear()
        if self._queue is not None:
            with contextlib.suppress(asyncio.QueueEmpty):
                while True:
                    self._queue.get_nowait()
                    self._queue.task_done()
        self._queue = None
        self._loop = None
        logger.info("AI analysis queue stopped")

    # -- producer ------------------------------------------------------
    def schedule(self, post_ids: Iterable[int]) -> int:
        """Enqueue post IDs for background analysis. Never blocks or raises.

        Returns the number of IDs actually accepted. Rejected IDs keep
        ``ai_status='pending'`` so the next scrape cycle picks them up, which
        makes overflow a backlog rather than data loss.
        """
        if self._paused:
            # Throttled: leave the posts untouched so the reclaim loop picks
            # them up after resume() instead of losing the work.
            ids = [int(pid) for pid in post_ids if pid]
            self.dropped += len(ids)
            logger.debug("AI queue paused; leaving %d post(s) pending", len(ids))
            return 0
        return self._enqueue(post_ids)

    def _enqueue(self, post_ids: Iterable[int]) -> int:
        ids = [int(pid) for pid in post_ids if pid]
        if not ids:
            return 0
        queue = self._queue
        loop = self._loop
        if queue is None or loop is None or loop.is_closed():
            logger.debug("AI queue not running; leaving %d post(s) pending", len(ids))
            self.dropped += len(ids)
            return 0

        accepted = 0
        for post_id in ids:
            try:
                queue.put_nowait(post_id)
                accepted += 1
            except asyncio.QueueFull:
                self.dropped += 1
                logger.warning(
                    "AI analysis queue is full (%d); post %s stays pending and will "
                    "be retried on the next cycle. Raise AI_QUEUE_MAXSIZE or lower "
                    "SCRAPING_INTERVAL_SECONDS.",
                    self._maxsize,
                    post_id,
                )
        self.enqueued += accepted
        return accepted

    # -- reclaim loop --------------------------------------------------
    async def _reclaim_loop(self) -> None:
        """Periodically re-enqueue posts the scraper never handed us.

        Runs in its own task on a fixed interval and exits quietly when paused,
        so throttling the queue also stops this database traffic.
        """
        interval = max(5, int(getattr(settings, "ai_reclaim_interval_seconds", 15) or 15))
        logger.info("AI reclaim loop started: interval=%ss", interval)
        while True:
            try:
                await asyncio.sleep(interval)
                if self._paused:
                    logger.debug("AI reclaim tick skipped: queue paused")
                    continue
                await self._reclaim_once()
            except asyncio.CancelledError:
                logger.info("AI reclaim loop stopped")
                return
            except Exception:
                # A failed tick must not kill the loop; posts stay claimable.
                logger.exception("AI reclaim tick failed")

    async def _reclaim_once(self) -> int:
        """Claim one bounded batch of pending/failed posts and queue them."""
        from app.db.session import SessionLocal
        from app.services.ai_orchestrator import claim_unanalyzed_posts

        limit = max(1, int(getattr(settings, "ai_reclaim_batch_size", 10) or 10))
        db = SessionLocal()
        try:
            # Sync ORM call, but it is a single indexed SELECT and the loop's own
            # task, so it cannot block request handling.
            posts = claim_unanalyzed_posts(db, batch_size=limit)
            post_ids = [post.id for post in posts]
        except Exception:
            logger.exception("AI reclaim could not claim posts")
            return 0
        finally:
            db.close()

        if not post_ids:
            return 0
        # schedule() re-checks the pause flag and the queue bound.
        accepted = self.schedule(post_ids)
        self.reclaimed += accepted
        if accepted:
            logger.info("AI reclaim re-queued %d post(s) from the backlog", accepted)
        return accepted

    @property
    def is_running(self) -> bool:
        return self._queue is not None and any(not t.done() for t in self._workers)

    def stats(self) -> dict[str, Any]:
        queue = self._queue
        return {
            "running": self.is_running,
            "paused": self.is_paused,
            "queued": queue.qsize() if queue is not None else 0,
            "maxsize": self._maxsize,
            "enqueued": self.enqueued,
            "processed": self.processed,
            "failed": self.failed,
            "dropped": self.dropped,
            "reclaimed": self.reclaimed,
        }

    # -- consumer ------------------------------------------------------
    async def _drain_batch(self, first_id: int) -> list[int]:
        """Collect up to ``ai_queue_batch_size`` IDs, coalescing a short window."""
        limit = max(1, int(getattr(settings, "ai_queue_batch_size", 10) or 10))
        batch = [first_id]
        queue = self._queue
        if queue is None:
            return batch
        # Coalesce: posts usually arrive in bursts, so waiting a beat lets one
        # provider call serve many posts.
        if queue.empty():
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(queue.get(), timeout=0.25)
        while len(batch) < limit:
            try:
                batch.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return batch

    async def _worker(self, index: int) -> None:
        """Consume batches until cancelled."""
        logger.debug("AI analysis worker %d started", index)
        while True:
            queue = self._queue
            if queue is None:
                return
            if self._paused:
                # Idle cheaply: sleep instead of spinning on a full queue, so a
                # paused worker costs nothing.
                await asyncio.sleep(1.0)
                continue
            try:
                first_id = await queue.get()
            except asyncio.CancelledError:
                return

            batch = [first_id]
            with contextlib.suppress(asyncio.CancelledError):
                batch = await self._drain_batch(first_id)

            for _ in batch:
                with contextlib.suppress(ValueError):
                    queue.task_done()

            try:
                await self._process_batch(batch)
            except asyncio.CancelledError:
                raise
            except Exception:
                # A batch failure must never kill the worker; the posts stay
                # 'pending'/'failed' in the database and are retried later.
                logger.exception("AI analysis batch of %d post(s) failed", len(batch))
                self.failed += len(batch)

    async def _process_batch(self, post_ids: list[int]) -> None:
        """Run one batch through the async orchestrator on a dedicated session."""
        from app.db.session import SessionLocal
        from app.services.ai_orchestrator import process_posts_by_ids_async

        db = SessionLocal()
        try:
            result = await process_posts_by_ids_async(db, post_ids)
        finally:
            db.close()

        self.processed += int(result.get("analyzed", 0)) + int(
            result.get("updated", 0)
        ) - int(result.get("analyzed", 0))
        if result.get("failed"):
            self.failed += int(result["failed"])
        logger.info(
            "AI batch complete: %d post(s) in %.1fs (%d analyzed, %d failed)",
            len(post_ids),
            float(result.get("duration_seconds", 0.0)),
            int(result.get("analyzed", 0)),
            int(result.get("failed", 0)),
        )


#: Process-wide singleton wired into the FastAPI lifespan.
ai_queue = AIAnalysisQueue()


def schedule_analysis(post_ids: Iterable[int]) -> int:
    """Module-level helper so callers do not import the instance directly."""
    return ai_queue.schedule(post_ids)


def pause_analysis() -> dict[str, Any]:
    """Throttle the worker. Posts stay 'pending' and resume picks them up."""
    ai_queue.pause()
    return ai_queue.stats()


def resume_analysis() -> dict[str, Any]:
    """Resume the worker and let the reclaim loop drain the backlog."""
    ai_queue.resume()
    return ai_queue.stats()

