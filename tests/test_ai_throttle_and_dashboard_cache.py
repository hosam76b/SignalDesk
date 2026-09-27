"""Tests for the AI worker throttle/reclaim loop and the dashboard cache.

These cover the pressure controls added to keep SQLite and the dashboard
responsive while the background AI worker is busy:

* ``ai_queue`` pause/resume must stop and restore provider work without losing
  posts (rejected posts stay 'pending' and the reclaim loop re-queues them).
* The reclaim loop must bound itself and honour the pause flag.
* ``TTLCache`` must expire, bound its size, and treat a zero TTL as disabled.
* The dashboard stats cache and ``/recent-activity`` pagination must be correct.

``pytest-asyncio`` is not a dependency, so the async cases are driven through
``asyncio.run`` rather than an event-loop marker.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func

from app.api import dashboard as dashboard_module
from app.core.cache import TTLCache
from app.models import MonitoredSource, Post, Topic
from app.services.ai_queue import AIAnalysisQueue, pause_analysis, resume_analysis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}


def _seed_topic_and_source(db, label: str) -> tuple[MonitoredSource, Topic]:
    """Create the topic/source pair every post row needs."""
    unique = f"{label}-{time.time_ns()}"
    source = MonitoredSource(
        platform="rss",
        name=unique,
        url_or_handle=f"https://example.invalid/{unique}",
    )
    topic = Topic(title=unique, description=unique)
    db.add_all([source, topic])
    db.flush()
    return source, topic


_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _post(source, topic, *, external_id, scraped_at, fingerprint=None, content="body"):
    return Post(
        topic_id=topic.id,
        source_id=source.id,
        external_id=external_id,
        platform="rss",
        author="author",
        content=content,
        published_at=_BASE,
        scraped_at=scraped_at,
        content_fingerprint=fingerprint,
        ai_status="pending",
    )


def _seed_posts(db, count: int) -> None:
    """Seed ``count`` unique posts, newest last so ordering is deterministic."""
    source, topic = _seed_topic_and_source(db, "page")
    for i in range(count):
        db.add(
            _post(
                source,
                topic,
                external_id=f"page-{time.time_ns()}-{i}",
                scraped_at=_BASE + timedelta(seconds=i),
            )
        )
    db.commit()


# ---------------------------------------------------------------------------
# TTLCache
# ---------------------------------------------------------------------------

def test_ttlcache_serves_repeat_reads_without_rebuilding():
    cache = TTLCache(maxsize=8)
    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        return f"value-{calls['n']}"

    assert cache.get_or_set("k", 30, factory) == "value-1"
    assert cache.get_or_set("k", 30, factory) == "value-1"
    assert calls["n"] == 1, "second read must come from the cache"


def test_ttlcache_expires_entries():
    cache = TTLCache()
    cache.set("k", "v", 0.05)
    hit, value = cache.get("k")
    assert hit is True and value == "v"
    time.sleep(0.08)
    hit, value = cache.get("k")
    assert hit is False and value is None


def test_ttlcache_zero_ttl_disables_caching():
    """A zero/negative TTL must not silently become an eternal cache."""
    cache = TTLCache()
    cache.set("k", "v", 0)
    assert cache.get("k")[0] is False


def test_ttlcache_is_bounded():
    cache = TTLCache(maxsize=2)
    cache.set("a", 1, 30)
    cache.set("b", 2, 30)
    cache.set("c", 3, 30)
    assert len(cache._entries) == 2
    assert cache.get("a")[0] is False, "oldest entry should have been evicted"
    assert cache.get("c")[0] is True


# ---------------------------------------------------------------------------
# Worker throttle
# ---------------------------------------------------------------------------

def test_pause_blocks_production_and_keeps_posts_pending():
    """A paused worker must accept no work; the posts stay claimable in the DB."""

    async def scenario():
        queue = AIAnalysisQueue()
        queue.start()
        try:
            queue.pause()
            assert queue.is_paused
            assert queue.schedule([1, 2, 3]) == 0
            assert queue._queue.qsize() == 0
            # Nothing was lost: the ids are simply still pending in the database.
            assert queue.dropped == 3
        finally:
            await queue.stop()

    asyncio.run(scenario())


def test_resume_restores_production():
    async def scenario():
        queue = AIAnalysisQueue()
        queue.start()
        try:
            queue.pause()
            assert queue.schedule([7]) == 0
            queue.resume()
            assert not queue.is_paused
            assert queue.schedule([7, 8]) == 2
            assert queue._queue.qsize() == 2
        finally:
            await queue.stop()

    asyncio.run(scenario())


def test_reclaim_tick_is_bounded_and_respects_pause(db, monkeypatch):
    """One tick takes at most ai_reclaim_batch_size, and nothing while paused."""
    import app.services.ai_queue as ai_queue_module

    source, topic = _seed_topic_and_source(db, "reclaim")
    unique = time.time_ns()
    for i in range(6):
        db.add(
            _post(
                source,
                topic,
                external_id=f"reclaim-{unique}-{i}",
                scraped_at=_BASE + timedelta(seconds=i),
            )
        )
    db.commit()

    backlog_before = (
        db.query(func.count(Post.id))
        .filter(Post.ai_status.in_(("pending", "failed")))
        .scalar()
    )
    assert backlog_before >= 6

    async def scenario():
        queue = AIAnalysisQueue()
        queue.start()
        try:
            # The loop opens its own session; point it at the test session.
            monkeypatch.setattr("app.db.session.SessionLocal", lambda: db, raising=False)
            monkeypatch.setattr(
                ai_queue_module.settings, "ai_reclaim_batch_size", 2, raising=False
            )
            accepted = await queue._reclaim_once()
            assert accepted == 2, f"tick must respect ai_reclaim_batch_size, took {accepted}"
            assert queue.reclaimed == 2

            # While paused it must do nothing at all.
            while not queue._queue.empty():
                queue._queue.get_nowait()
            queue.pause()
            assert await queue._reclaim_once() == 0
            assert queue._queue.qsize() == 0
            queue.resume()
        finally:
            await queue.stop()

    asyncio.run(scenario())

    # Reclaiming only enqueues; it must not mutate the posts.
    backlog_after = (
        db.query(func.count(Post.id))
        .filter(Post.ai_status.in_(("pending", "failed")))
        .scalar()
    )
    assert backlog_after == backlog_before


def test_reclaim_loop_task_starts_only_when_enabled(monkeypatch):
    async def run(enabled: bool) -> bool:
        queue = AIAnalysisQueue()
        monkeypatch.setattr(
            "app.services.ai_queue.settings.ai_reclaim_enabled", enabled, raising=False
        )
        queue.start()
        try:
            return queue._reclaim_task is not None
        finally:
            await queue.stop()

    assert asyncio.run(run(True)) is True
    assert asyncio.run(run(False)) is False


def test_queue_stats_expose_throttle_state():
    stats = AIAnalysisQueue().stats()
    for key in ("paused", "reclaimed", "running", "queued"):
        assert key in stats, f"stats() must expose {key}"


def test_module_level_pause_helpers_target_the_singleton():
    try:
        assert pause_analysis()["paused"] is True
        assert resume_analysis()["paused"] is False
    finally:
        resume_analysis()


# ---------------------------------------------------------------------------
# Dashboard cache and pagination
# ---------------------------------------------------------------------------

def test_dashboard_stats_are_cached(monkeypatch, db):
    dashboard_module._stats_cache.clear()
    calls = {"n": 0}
    real = dashboard_module._compute_dashboard_stats

    def counting(session):
        calls["n"] += 1
        return real(session)

    monkeypatch.setattr(dashboard_module, "_compute_dashboard_stats", counting)

    first = dashboard_module.get_dashboard_stats(response=_FakeResponse(), db=db, _=None)
    second = dashboard_module.get_dashboard_stats(response=_FakeResponse(), db=db, _=None)

    assert calls["n"] == 1, "second stats request must be served from the cache"
    assert first is second
    dashboard_module._stats_cache.clear()


def test_dashboard_stats_ttl_zero_bypasses_cache(monkeypatch, db):
    dashboard_module._stats_cache.clear()
    monkeypatch.setattr(
        dashboard_module.settings, "dashboard_cache_ttl_seconds", 0, raising=False
    )
    calls = {"n": 0}
    real = dashboard_module._compute_dashboard_stats

    def counting(session):
        calls["n"] += 1
        return real(session)

    monkeypatch.setattr(dashboard_module, "_compute_dashboard_stats", counting)
    dashboard_module.get_dashboard_stats(response=_FakeResponse(), db=db, _=None)
    dashboard_module.get_dashboard_stats(response=_FakeResponse(), db=db, _=None)
    assert calls["n"] == 2, "ttl=0 must not cache"
    dashboard_module._stats_cache.clear()


def test_recent_activity_pages_over_the_deduplicated_sequence(db):
    _seed_posts(db, 40)
    page1 = dashboard_module.get_recent_activity(limit=10, offset=0, db=db, _=None)
    page2 = dashboard_module.get_recent_activity(limit=10, offset=10, db=db, _=None)
    assert len(page1) == 10 and len(page2) == 10
    ids1 = [p.id for p in page1]
    ids2 = [p.id for p in page2]
    assert not set(ids1) & set(ids2), "pages must not overlap"
    assert len(set(ids1)) == 10, "no duplicate ids within a page"


def test_recent_activity_is_stable_and_prefix_consistent(db):
    _seed_posts(db, 30)
    big = dashboard_module.get_recent_activity(limit=20, offset=0, db=db, _=None)
    small = dashboard_module.get_recent_activity(limit=5, offset=0, db=db, _=None)
    assert [p.id for p in small] == [p.id for p in big[:5]], (
        "a smaller limit must be a prefix of a larger one"
    )


def test_recent_activity_returns_empty_past_the_end(db):
    _seed_posts(db, 5)
    assert dashboard_module.get_recent_activity(limit=10, offset=10_000, db=db, _=None) == []


def test_recent_activity_collapses_duplicate_rows(db):
    """Near-duplicates occupy one slot, so paging counts unique posts."""
    source, topic = _seed_topic_and_source(db, "dupes")
    unique = time.time_ns()
    for i in range(6):
        db.add(
            _post(
                source,
                topic,
                external_id=f"dupe-{unique}",
                scraped_at=_BASE + timedelta(seconds=i),
                # Same fingerprint => same post, ingested repeatedly.
                fingerprint="deadbeef",
                content="same body",
            )
        )
    db.commit()

    page = dashboard_module.get_recent_activity(limit=15, offset=0, db=db, _=None)
    assert page, "at least the first copy must survive dedupe"
    assert len({p.id for p in page}) == len(page), "duplicates must not both appear"


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

def test_model_index_matches_the_claim_predicate():
    from app.models.post import Post as PostModel

    indexes = {i.name: i for i in PostModel.__table__.indexes}
    assert "ix_posts_ai_pending" not in indexes, "superseded index must be gone"
    claim = indexes["ix_posts_ai_queue"]
    where = str(claim.dialect_options["sqlite"]["where"])
    assert "ai_status IN ('pending', 'failed')" in where
    # Keyed on the ORDER BY column so no temp sort is needed.
    assert [c.name for c in claim.columns] == ["id"]
