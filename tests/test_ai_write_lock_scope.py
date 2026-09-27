"""Regression tests for SQLite write-lock scope in the AI analysis pipeline.

Background
----------
``_process_posts_async`` used to open a write transaction (via
``mark_processing``) and then ``await`` the provider fan-out before committing.
SQLite permits exactly one writer, so for the whole duration of the model call
-- measured at 98-174s per batch -- every other writer in the process was
blocked. After ``busy_timeout`` (15s) they failed with
``sqlite3.OperationalError: database is locked``, which surfaced to users as
HTTP 500 on unrelated endpoints. The captured production failure was
``POST /api/auth/login`` dying on ``UPDATE users SET last_login_at``.

The invariant under test is therefore narrow and specific: while the provider
is being called, no *other* connection may be blocked from committing.

Note that a read transaction legitimately *is* open at that point (Phase 1 runs
SELECTs to build prompts). WAL mode lets readers run concurrently with the
single writer, so an open read transaction is not the bug and is not asserted
against here. The lock-scope tests therefore use a real file-backed database
and a genuinely separate connection, because ``StaticPool`` hands out the same
DBAPI connection and would make a contention test vacuous.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.post import (
    AI_STATUS_DONE,
    AI_STATUS_PENDING,
    AI_STATUS_PROCESSING,
    Post,
)
from app.models.source import MonitoredSource
from app.models.topic import Topic
from app.services import ai_orchestrator
from app.services.ai_orchestrator import process_posts_by_ids_async


def _build_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _record):  # pragma: no cover - trivial
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=1000")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return engine


def _seed(session) -> None:
    source = MonitoredSource(
        name="test-source",
        platform="rss",
        url_or_handle="https://example.invalid/rss",
    )
    session.add(source)
    session.flush()
    topic = Topic(title="Test Topic", description="d")
    session.add(topic)
    session.flush()
    session.add(
        Post(
            source_id=source.id,
            topic_id=topic.id,
            title="Some headline about an incident",
            content="A body long enough to be analysed by the model pipeline.",
            post_url="https://example.invalid/a",
            external_id="ext-1",
            platform="rss",
            author="someone",
            published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )
    session.commit()


@pytest.fixture()
def memory_db():
    engine = _build_engine("sqlite://")
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    _seed(session)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def file_db(tmp_path):
    """A real file-backed database, so a second connection truly contends."""
    engine = _build_engine(f"sqlite:///{tmp_path/'posts.db'}")
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    _seed(session)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _analysis(post_id: int) -> dict:
    return {
        "success": True,
        "ai_summary": "A summary.",
        "violence_category": None,
        "severity_level": "low",
        "is_flagged": False,
        "detected_entities": [],
        "raw_response": {"ok": True},
    }


def _status(session, post_id: int = 1) -> str:
    session.expire_all()
    return session.query(Post).filter(Post.id == post_id).one().ai_status


# ---------------------------------------------------------------------------
# The core regression: a second writer must not be blocked during the fan-out.
# ---------------------------------------------------------------------------

def test_second_writer_can_commit_during_provider_call(file_db, monkeypatch):
    """An unrelated writer must be able to commit while the model is running.

    This is the user-visible symptom. Before the fix this write blocked for the
    full duration of the provider call and then raised "database is locked".
    """
    outcome: dict[str, str] = {}

    async def slow_analyze(tasks):
        def other_writer():
            # A genuinely separate connection on the same file, like the
            # request-scoped session a login request would use.
            try:
                other = sqlite3.connect(
                    file_db.get_bind().url.database, timeout=1.0
                )
                other.execute("UPDATE posts SET title = 'touched' WHERE id = 1")
                other.commit()
                other.close()
                outcome["status"] = "committed"
            except sqlite3.OperationalError as exc:
                outcome["status"] = f"blocked: {exc}"

        thread = threading.Thread(target=other_writer)
        thread.start()
        thread.join(timeout=30)
        if thread.is_alive():
            outcome["status"] = "blocked: thread never finished"
        return {task.post_id: _analysis(task.post_id) for task in tasks}

    monkeypatch.setattr(ai_orchestrator, "_analyze_tasks", slow_analyze)

    result = asyncio.run(process_posts_by_ids_async(file_db, [1]))

    assert result["analyzed"] == 1
    assert outcome.get("status") == "committed", (
        "a second writer could not commit while the provider was being called; "
        "this is the lock that turned POST /api/auth/login into a 500"
    )


def test_lock_is_released_before_provider_call_starts(file_db, monkeypatch):
    """The claim commit must happen before the fan-out, not after it."""
    outcome: dict[str, str] = {}

    async def probe(tasks):
        try:
            other = sqlite3.connect(file_db.get_bind().url.database, timeout=1.0)
            other.execute("UPDATE posts SET title = 'touched' WHERE id = 1")
            other.commit()
            other.close()
            outcome["status"] = "committed"
        except sqlite3.OperationalError as exc:
            outcome["status"] = f"blocked: {exc}"
        return {task.post_id: _analysis(task.post_id) for task in tasks}

    monkeypatch.setattr(ai_orchestrator, "_analyze_tasks", probe)

    asyncio.run(process_posts_by_ids_async(file_db, [1]))

    assert outcome.get("status") == "committed"


def test_claim_is_committed_before_the_provider_call(file_db, monkeypatch):
    """A second connection must see the in-flight claim.

    Proves the claim is committed (not merely flushed) before the fan-out, so a
    concurrent worker cannot double-claim the same posts.
    """
    seen: list[str] = []

    async def fake_analyze(tasks):
        other = sqlite3.connect(file_db.get_bind().url.database, timeout=1.0)
        seen.append(other.execute("SELECT ai_status FROM posts WHERE id = 1").fetchone()[0])
        other.close()
        return {task.post_id: _analysis(task.post_id) for task in tasks}

    monkeypatch.setattr(ai_orchestrator, "_analyze_tasks", fake_analyze)

    asyncio.run(process_posts_by_ids_async(file_db, [1]))

    assert seen == [AI_STATUS_PROCESSING]


def test_batch_still_records_results(file_db, monkeypatch):
    """The fix must not lose the analysis it was protecting."""
    async def fake_analyze(tasks):
        return {task.post_id: _analysis(task.post_id) for task in tasks}

    monkeypatch.setattr(ai_orchestrator, "_analyze_tasks", fake_analyze)

    result = asyncio.run(process_posts_by_ids_async(file_db, [1]))

    assert result["success"] is True
    assert result["analyzed"] == 1
    assert _status(file_db) == AI_STATUS_DONE


# ---------------------------------------------------------------------------
# The claim is now durable, so it must be handed back on every failure path.
# ---------------------------------------------------------------------------

def test_claim_is_released_when_the_fan_out_is_cancelled(memory_db, monkeypatch):
    """A cancelled batch must not strand posts in 'processing'.

    ai_queue.stop() cancels workers on every shutdown, and the fan-out is the
    only suspension point in the function, so this is a routine event rather
    than a rare one. Nothing revisits a post left in 'processing': both the
    claim query and the reclaim loop filter on pending/failed only.
    """
    started = asyncio.Event()

    async def cancelling_analyze(tasks):
        started.set()
        await asyncio.sleep(30)
        return {}

    monkeypatch.setattr(ai_orchestrator, "_analyze_tasks", cancelling_analyze)

    async def run():
        task = asyncio.ensure_future(process_posts_by_ids_async(memory_db, [1]))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())

    status = _status(memory_db)
    assert status == AI_STATUS_PENDING, (
        f"post stranded in {status!r}; the reclaim loop will never retry it"
    )


def test_claim_is_released_when_the_final_commit_fails(memory_db, monkeypatch):
    """A failed result commit must return the posts to the queue as well."""
    async def fake_analyze(tasks):
        return {task.post_id: _analysis(task.post_id) for task in tasks}

    monkeypatch.setattr(ai_orchestrator, "_analyze_tasks", fake_analyze)

    real_commit = memory_db.commit
    state = {"calls": 0}

    def flaky_commit():
        # The first commit is the claim and must succeed; the second is the
        # result commit, which is the one being simulated as failing.
        state["calls"] += 1
        if state["calls"] == 1:
            return real_commit()
        raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(memory_db, "commit", flaky_commit)

    result = asyncio.run(process_posts_by_ids_async(memory_db, [1]))

    assert result["success"] is False
    monkeypatch.undo()
    assert _status(memory_db) == AI_STATUS_PENDING


def test_release_claim_leaves_terminal_statuses_alone(memory_db, monkeypatch):
    """``release_claim`` must not resurrect a post that already has a verdict."""
    async def fake_analyze(tasks):
        return {task.post_id: _analysis(task.post_id) for task in tasks}

    monkeypatch.setattr(ai_orchestrator, "_analyze_tasks", fake_analyze)
    asyncio.run(process_posts_by_ids_async(memory_db, [1]))
    assert _status(memory_db) == AI_STATUS_DONE

    # A late cancellation must not undo the recorded analysis.
    assert ai_orchestrator.release_claim(memory_db, [1]) == 0
    memory_db.commit()
    assert _status(memory_db) == AI_STATUS_DONE


def test_release_claim_returns_in_flight_posts(memory_db):
    """Sanity check for the helper the failure paths depend on."""
    assert ai_orchestrator.release_claim(memory_db, []) == 0

    memory_db.query(Post).filter(Post.id == 1).update(
        {Post.ai_status: AI_STATUS_PROCESSING}, synchronize_session=False
    )
    memory_db.commit()

    assert ai_orchestrator.release_claim(memory_db, [1]) == 1
    memory_db.commit()
    assert _status(memory_db) == AI_STATUS_PENDING
