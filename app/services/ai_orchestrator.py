"""Concurrent batch orchestration for multi-provider post analysis.

Concurrency model
-----------------
Every public entry point exists in two forms:

* ``*_async`` -- awaits provider calls directly. Safe to call from ``async def``
  endpoints and from the background worker, because the event loop keeps
  running and other requests are served normally.
* synchronous -- a thin wrapper that calls the async form through
  ``run_sync``. Retained for ``def`` endpoints (FastAPI already runs those in a
  worker thread) and for existing callers/tests.

The ingestion path -- ``scraper_orchestrator._save_posts`` and
``api/ingestion/quick_ingest_url`` -- uses the async form or the bounded queue
in ``app/services/ai_queue.py``. It must never use the synchronous form from
inside ``async def``: that blocked the event loop for the entire batch and froze
the whole server (measured 100% of a 30.3s batch, ``/health`` p95 30,229 ms).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.keyword import Keyword
from app.models.post import (
    AI_STATUS_DONE,
    AI_STATUS_FAILED,
    AI_STATUS_PENDING,
    AI_STATUS_PROCESSING,
    AI_STATUS_SKIPPED,
    Post,
)
from app.models.topic import PromptTemplate, Topic
from app.services.ai_service import (
    ai_service,
    fallback_result,
    run_sync,
    wrap_untrusted,
)
from app.services.knowledge_context import get_topic_knowledge_context
from app.services.media_processor import build_combined_text, collect_image_refs, load_inline_images
from app.services.risk_signals import apply_risk_signals
from app.services.sentiment import analyze_sentiment
from app.services.webhook_service import WEBHOOK_EVENT_ANALYSIS_COMPLETED, dispatch_event
from config import settings

logger = logging.getLogger(__name__)

#: Article text sent to the model is capped. Must stay comfortably below
#: ``ollama_num_ctx`` so system prompt + knowledge context + article all fit.
MAX_ARTICLE_CHARS = 6000


@dataclass(slots=True)
class _AnalysisTask:
    """Everything one post needs for analysis, detached from the DB session."""

    post_id: int
    prompt_text: str
    combined_text: str = ""
    image_refs: list[str] = field(default_factory=list)


def _latest_active_prompt(db: Session, topic_id: int) -> PromptTemplate | None:
    """Return the newest active prompt template for a topic, if one exists."""
    return (
        db.query(PromptTemplate)
        .filter(PromptTemplate.topic_id == topic_id, PromptTemplate.is_active == 1)
        .order_by(PromptTemplate.updated_at.desc(), PromptTemplate.id.desc())
        .first()
    )


def _topic_keywords(db: Session, topic_id: int) -> str:
    keywords = (
        db.query(Keyword)
        .filter(Keyword.topic_id == topic_id, Keyword.is_active.is_(True))
        .order_by(Keyword.id.asc())
        .limit(50)
        .all()
    )
    return ", ".join(keyword.word_or_phrase for keyword in keywords) or "No active keywords configured."


def _post_context(post: Post, combined_text: str) -> str:
    """Render one post for the prompt with the article text fenced.

    The fencing (``<<<ARTICLE>>>``/``<<<END>>>``) plus the matching
    instruction in the system prompt is what keeps crawled text from being
    read as instructions by the model.
    """
    return "\n".join([
        f"- ID: {post.id}",
        f"  Platform: {post.platform}",
        f"  Author: {post.author}",
        f"  Published: {post.published_at.isoformat() if post.published_at else 'unknown'}",
        f"  Title: {post.title or ''}",
        f"  Content: {wrap_untrusted(combined_text, max_chars=MAX_ARTICLE_CHARS)}",
    ])


def _render_analysis_prompt(db: Session, post: Post, combined_text: str, knowledge_context: str) -> str:
    topic = db.query(Topic).filter(Topic.id == post.topic_id).first()
    prompt_template = _latest_active_prompt(db, post.topic_id)
    post_context = _post_context(post, combined_text)
    context = {
        "topic_name": topic.title if topic else "Topic",
        "posts_content": post_context,
        "post_content": combined_text,
        "keywords": _topic_keywords(db, post.topic_id),
        "time_range": "current post",
        "knowledge_context": knowledge_context or "No knowledge base documents for this topic.",
    }

    if prompt_template is None:
        return (
            f"[Topic]: {context['topic_name']}\n"
            f"[Keywords]: {context['keywords']}\n"
            f"[Reference context from the topic's knowledge base]:\n{knowledge_context}\n\n"
            f"[Post content]:\n{post_context}"
        )

    rendered = prompt_template.template
    for key, value in context.items():
        rendered = rendered.replace(f"{{{key}}}", str(value))

    has_post_placeholder = "{posts_content}" in prompt_template.template or "{post_content}" in prompt_template.template
    has_knowledge_placeholder = "{knowledge_context}" in prompt_template.template
    if not has_post_placeholder:
        rendered = (
            f"{rendered}\n\n"
            "[Actual monitored content for this analysis]\n"
            f"Topic: {context['topic_name']}\n"
            f"Time range: {context['time_range']}\n"
            f"Keywords: {context['keywords']}\n\n"
            f"Post:\n{post_context}"
        )
    if not has_knowledge_placeholder:
        rendered = f"{rendered}\n\nKnowledge context:\n{context['knowledge_context']}"
    return rendered


def _sentiment_fallback_summary(analysis: dict[str, Any]) -> str | None:
    """Summary to persist when no provider produced one.

    Two cases, and the difference matters:

    * The deterministic rule engine flagged a risk. The post is fully assessed
      without the model, so the right value is NULL -- writing prose here would
      present rule-engine output as if the LLM had written it. The risk detail
      is already carried by violence_category / severity_level / is_flagged.
    * Nothing matched, but local sentiment analysis did run. The analyst still
      gets a human-readable note explaining why there is no model summary, so
      an empty field is not read as "analysis silently lost".
    """
    if analysis.get("risk_signals"):
        return None
    return "تم تحليل المشاعر محلياً؛ لم يتوفر مزود ذكاء اصطناعي لإنتاج ملخص متقدم."


async def _analyze_tasks(tasks: list[_AnalysisTask]) -> dict[int, dict[str, Any]]:
    """Run provider calls concurrently under a bounded semaphore."""
    limit = max(1, int(getattr(settings, "ai_max_concurrency", 5) or 5))
    semaphore = asyncio.Semaphore(limit)
    max_images = max(0, int(getattr(settings, "ai_max_images_per_post", 2) or 0))
    use_vision = max_images > 0 and ai_service.supports_vision

    async def _run(task: _AnalysisTask) -> tuple[int, dict[str, Any]]:
        async with semaphore:
            images = await load_inline_images(task.image_refs, max_images) if (use_vision and task.image_refs) else []
            return task.post_id, await ai_service.analyze_post_content_async(task.prompt_text, images)

    outcomes = await asyncio.gather(*(_run(task) for task in tasks), return_exceptions=True)
    analyses: dict[int, dict[str, Any]] = {}
    for task, outcome in zip(tasks, outcomes):
        if isinstance(outcome, BaseException):
            logger.error("Analysis task failed for post %s: %s", task.post_id, outcome)
            analyses[task.post_id] = fallback_result(str(outcome))
        else:
            analyses[outcome[0]] = outcome[1]
    return analyses


# ---------------------------------------------------------------------------
# Claiming posts
# ---------------------------------------------------------------------------

def claim_unanalyzed_posts(db: Session, batch_size: int = 50) -> list[Post]:
    """Select a batch of posts awaiting analysis, oldest first.

    Selection is driven by the indexed ``ai_status`` column rather than
    ``ai_summary IS NULL OR ai_summary = ''``. The previous predicate forced a
    full table scan plus a temp B-tree sort on every call (measured 99 ms and
    growing linearly with table size).

    Ordering is ascending by id rather than ``scraped_at DESC`` so the partial
    index ``ix_posts_ai_pending`` is usable and the queue is drained FIFO.
    """
    return (
        db.query(Post)
        .filter(Post.ai_status.in_((AI_STATUS_PENDING, AI_STATUS_FAILED)))
        .order_by(Post.id.asc())
        .limit(batch_size)
        .all()
    )


def mark_processing(db: Session, post_ids: list[int]) -> None:
    """Flag posts as in-flight so a second worker does not claim them."""
    if not post_ids:
        return
    db.query(Post).filter(Post.id.in_(post_ids)).update(
        {Post.ai_status: AI_STATUS_PROCESSING},
        synchronize_session=False,
    )


def release_claim(db: Session, post_ids: list[int]) -> int:
    """Return still-in-flight posts to the pending pool.

    The claim is committed *before* the provider fan-out so the write lock is
    not held across the network call (see ``_process_posts_async``). That makes
    the claim durable, so a rollback no longer returns those posts to the queue
    on their own -- they have to be handed back explicitly. Only posts still
    marked ``processing`` are touched, so a batch that already recorded a
    terminal status keeps it.

    Returns:
        int: Number of posts moved back to ``pending``.
    """
    if not post_ids:
        return 0
    return db.query(Post).filter(
        Post.id.in_(post_ids),
        Post.ai_status == AI_STATUS_PROCESSING,
    ).update(
        {Post.ai_status: AI_STATUS_PENDING},
        synchronize_session=False,
    )


# ---------------------------------------------------------------------------
# Public entry points (async)
# ---------------------------------------------------------------------------

async def process_unanalyzed_posts_async(db: Session, batch_size: int = 50) -> dict[str, Any]:
    """Analyze up to ``batch_size`` pending posts concurrently and commit results."""
    if batch_size < 1:
        raise ValueError("batch_size must be greater than zero")
    posts = claim_unanalyzed_posts(db, batch_size=batch_size)
    return await _process_posts_async(db, posts)


async def process_posts_by_ids_async(db: Session, post_ids: list[int]) -> dict[str, Any]:
    """Analyze the specified posts, preserving ingestion order as much as possible."""
    clean_ids = list(dict.fromkeys(int(post_id) for post_id in post_ids if post_id))
    if not clean_ids:
        return await _process_posts_async(db, [])
    posts = db.query(Post).filter(Post.id.in_(clean_ids)).all()
    posts_by_id = {post.id: post for post in posts}
    ordered = [posts_by_id[post_id] for post_id in clean_ids if post_id in posts_by_id]
    return await _process_posts_async(db, ordered)


# ---------------------------------------------------------------------------
# Public entry points (synchronous, for `def` endpoints and scripts)
# ---------------------------------------------------------------------------

def process_unanalyzed_posts(db: Session, batch_size: int = 50) -> dict[str, Any]:
    """Analyze up to ``batch_size`` pending posts concurrently and commit their results.

    Blocking. Only safe from a synchronous context (a ``def`` FastAPI endpoint,
    a CLI script, a worker thread). Use ``process_unanalyzed_posts_async``
    from ``async def`` code.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be greater than zero")
    posts = claim_unanalyzed_posts(db, batch_size=batch_size)
    return run_sync(_process_posts_async(db, posts))


def process_posts_by_ids(db: Session, post_ids: list[int]) -> dict[str, Any]:
    """Blocking variant of :func:`process_posts_by_ids_async`."""
    clean_ids = list(dict.fromkeys(int(post_id) for post_id in post_ids if post_id))
    if not clean_ids:
        return run_sync(_process_posts_async(db, []))
    posts = db.query(Post).filter(Post.id.in_(clean_ids)).all()
    posts_by_id = {post.id: post for post in posts}
    return run_sync(
        _process_posts_async(db, [posts_by_id[post_id] for post_id in clean_ids if post_id in posts_by_id])
    )


def auto_analyze_posts(db: Session, post_ids: list[int]) -> dict[str, Any]:
    """Best-effort automatic analysis for newly ingested posts.

    .. deprecated::
       Blocking. From ``async def`` code enqueue instead::

           from app.services.ai_queue import schedule_analysis
           schedule_analysis(post_ids)
    """
    try:
        return process_posts_by_ids(db, post_ids)
    except Exception as exc:
        logger.exception("Automatic post analysis failed: %s", exc)
        return {"success": False, "processed": 0, "analyzed": 0, "updated": 0, "failed": len(post_ids), "errors": [str(exc)]}


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

async def _process_posts_async(db: Session, posts: list[Post]) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    result: dict[str, Any] = {
        "success": True,
        "processed": len(posts),
        "analyzed": 0,
        "updated": 0,
        "failed": 0,
        "risk_flagged": 0,
        "errors": [],
        "duration_seconds": 0.0,
    }

    max_images = max(0, int(getattr(settings, "ai_max_images_per_post", 2) or 0))
    posts_by_id = {post.id: post for post in posts}
    tasks: list[_AnalysisTask] = []
    skipped_empty = 0

    if posts:
        # Mark in-flight up front so a concurrent worker cannot double-claim.
        mark_processing(db, [post.id for post in posts])
        # Commit the claim before the provider fan-out below. This await lasts
        # as long as the model takes (measured 98-174s per batch), and SQLite
        # allows exactly one writer: holding this transaction across it made
        # every other writer in the process fail with "database is locked"
        # after busy_timeout. That surfaced as HTTP 500 on unrelated endpoints
        # -- POST /api/auth/login died on "UPDATE users SET last_login_at".
        # The claim is made durable on purpose, so release_claim() is now
        # responsible for handing the posts back if the fan-out is cancelled.
        db.commit()

    # Phase 1: build prompts on the session thread so no DB access happens concurrently.
    for post in posts:
        try:
            # Merge raw text with any OCR/audio-transcript results for unified analysis.
            combined_text = build_combined_text(post)
            local_sentiment = analyze_sentiment(combined_text)
            post.sentiment = local_sentiment["label"]
            post.sentiment_score = int(float(local_sentiment["score"]) * 100)

            if not combined_text:
                post.violence_category = None
                post.severity_level = "low"
                post.ai_summary = "لا يوجد محتوى نصي قابل للتحليل"
                post.raw_ai_response = {"skipped": "empty_content"}
                post.is_flagged = False
                # Store NULL rather than '' so the partial pending index stays
                # fully usable; an empty-string sentinel defeats it.
                post.ai_status = AI_STATUS_SKIPPED
                post.ai_analyzed_at = datetime.now(timezone.utc)
                skipped_empty += 1
                continue

            knowledge_context = get_topic_knowledge_context(db, post.topic_id, query=combined_text)
            prompt_text = _render_analysis_prompt(db, post, combined_text, knowledge_context)
            tasks.append(_AnalysisTask(
                post_id=post.id,
                prompt_text=prompt_text,
                combined_text=combined_text,
                image_refs=collect_image_refs(post, max_images) if max_images else [],
            ))
        except Exception as exc:
            logger.exception("Failed to prepare post %s for analysis: %s", post.id, exc)
            post.ai_status = AI_STATUS_FAILED
            result["failed"] += 1
            result["errors"].append({"post_id": post.id, "error": str(exc)})

    # Phase 2: fan out the provider calls concurrently. This awaits, so the
    # event loop stays free to serve other requests for the whole duration.
    #
    # This is the only suspension point in the function, so it is the only place
    # a CancelledError can land -- and ai_queue.stop() cancels workers on every
    # shutdown. BaseException is deliberate: CancelledError does not derive from
    # Exception, and an unhandled one would strand the claimed posts in
    # 'processing', which neither the claim query nor the reclaim loop revisits.
    try:
        analyses = await _analyze_tasks(tasks) if tasks else {}
    except BaseException:
        with contextlib.suppress(Exception):
            release_claim(db, [post.id for post in posts])
            db.commit()
        raise
    text_by_post = {task.post_id: task.combined_text for task in tasks}
    has_pending_writes = bool(posts)
    sentiment_fallbacks = 0
    analyzed_at = datetime.now(timezone.utc)

    for post_id, analysis in analyses.items():
        post = posts_by_id.get(post_id)
        if post is None:
            continue

        # Rule-based screening runs on every outcome so explicit self-harm/violence
        # is never left unflagged when the model fails or under-rates it.
        analysis = apply_risk_signals(analysis, text_by_post.get(post_id, ""))

        if not analysis["success"]:
            result["failed"] += 1
            result["errors"].append({"post_id": post_id, "error": analysis["error"]})
            post.violence_category = analysis.get("violence_category")
            post.severity_level = analysis.get("severity_level") or "low"
            # NULL rather than '' when no model summary exists, so the partial
            # index stays fully usable and no empty-string sentinel is written.
            post.ai_summary = _sentiment_fallback_summary(analysis)
            post.raw_ai_response = analysis.get("raw_response") or {"error": analysis.get("error")}
            post.is_flagged = bool(analysis.get("is_flagged"))
            if analysis.get("risk_signals"):
                post.is_dangerous = True
                result["risk_flagged"] += 1
            # Leave a retryable failure claimable rather than terminal, so a
            # recovered provider picks the post up on a later cycle. A post that
            # tripped the deterministic rule engine is already fully assessed
            # though, so it is terminal -- re-running a model over it would only
            # risk it downgrading the severity the rule engine set.
            post.ai_status = AI_STATUS_DONE if analysis.get("risk_signals") else AI_STATUS_FAILED
            post.ai_analyzed_at = analyzed_at
            sentiment_fallbacks += 1
            continue

        post.violence_category = analysis["violence_category"]
        post.severity_level = analysis["severity_level"]
        post.ai_summary = analysis["ai_summary"] or None
        post.raw_ai_response = analysis["raw_response"]
        post.is_flagged = analysis["is_flagged"]
        post.ai_status = AI_STATUS_DONE
        post.ai_analyzed_at = analyzed_at
        if analysis.get("risk_signals"):
            post.is_dangerous = True
            result["risk_flagged"] += 1
        if analysis.get("detected_entities"):
            post.entities = analysis["detected_entities"]
        result["analyzed"] += 1

    if result["analyzed"] or skipped_empty or has_pending_writes:
        try:
            db.commit()
            result["updated"] = result["analyzed"] + skipped_empty + sentiment_fallbacks
        except Exception as exc:
            db.rollback()
            # The claim was committed before the fan-out, so this rollback no
            # longer returns the posts to the queue. Hand them back explicitly
            # or they stay 'processing' forever.
            with contextlib.suppress(Exception):
                release_claim(db, [post.id for post in posts])
                db.commit()
            result["success"] = False
            result["errors"].append({"error": f"Database commit failed: {exc}"})
            result["updated"] = 0

    if result["updated"]:
        try:
            # Awaited, not dispatch_event_blocking(): that one performs blocking
            # httpx calls, and running it here froze the whole event loop for the
            # duration of every webhook POST, so no endpoint could be served
            # meanwhile. dispatch_event() uses httpx.AsyncClient and yields at
            # each request.
            await dispatch_event(db, WEBHOOK_EVENT_ANALYSIS_COMPLETED, {
                "processed": result["processed"],
                "analyzed": result["analyzed"],
                "failed": result["failed"],
                "duration_seconds": result["duration_seconds"],
            })
        except Exception:
            logger.exception("analysis_completed webhook dispatch failed")

    result["duration_seconds"] = (datetime.now(timezone.utc) - started_at).total_seconds()
    return result


class AIOrchestrator:
    """Compatibility wrapper around the module-level batch processor."""

    def process_unanalyzed_posts(self, db: Session, batch_size: int = 50) -> dict[str, Any]:
        """Process a bounded batch of pending posts (blocking; `def` endpoints only)."""
        return process_unanalyzed_posts(db, batch_size)

    async def process_unanalyzed_posts_async(self, db: Session, batch_size: int = 50) -> dict[str, Any]:
        """Process a bounded batch of pending posts without blocking the loop."""
        return await process_unanalyzed_posts_async(db, batch_size)

    def get_flagged_posts(
        self,
        db: Session,
        severity_level: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return flagged posts and all high/critical posts with pagination."""
        query = db.query(Post).filter(
            (Post.is_flagged.is_(True)) | (Post.severity_level.in_(["high", "critical"]))
        )
        if severity_level:
            if severity_level not in {"low", "medium", "high", "critical"}:
                raise ValueError("Invalid severity level")
            query = query.filter(Post.severity_level == severity_level)

        posts = query.order_by(Post.id.desc()).offset(offset).limit(limit).all()
        return {
            "success": True,
            "total_count": query.count(),
            "returned": len(posts),
            "limit": limit,
            "offset": offset,
            "posts": [
                {
                    "id": post.id,
                    "source": post.source.name if post.source else "Unknown",
                    "source_id": post.source_id,
                    "platform": post.platform,
                    "author": post.author,
                    "content": post.content[:500],
                    "post_url": post.post_url,
                    "published_at": post.published_at.isoformat() if post.published_at else None,
                    "scraped_at": post.scraped_at.isoformat() if post.scraped_at else None,
                    "severity_level": post.severity_level,
                    "violence_category": post.violence_category,
                    "ai_summary": post.ai_summary,
                    "is_flagged": post.is_flagged,
                }
                for post in posts
            ],
        }


ai_orchestrator = AIOrchestrator()
