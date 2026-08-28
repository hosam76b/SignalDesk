"""Phase 3 topic-scoped ingestion and n8n payload tests."""

from datetime import datetime, timezone
import asyncio

from app.models import Keyword, Post
from app.services.scraper_orchestrator import ScraperOrchestrator
from app.services.webhook_service import build_n8n_post_payload


def test_targeted_ingestion_scopes_sources_keywords_and_posts(db, seeded_db, monkeypatch):
    db.query(Post).delete()
    db.commit()
    orchestrator = ScraperOrchestrator()
    calls = []

    async def fake_scrape(source, keywords):
        calls.append((source.id, list(keywords)))
        return [{
            "external_id": f"targeted-{source.id}",
            "platform": source.platform,
            "author": "fixture",
            "title": "alpha result",
            "content": "alpha result only",
            "published_at": datetime.now(timezone.utc),
        }]

    async def fake_dispatch(_payload):
        return {"delivered": False, "error": "Webhook URL is not configured"}

    monkeypatch.setattr(orchestrator, "_scrape_source", fake_scrape)
    monkeypatch.setattr("app.services.scraper_orchestrator.dispatch_post_ingested", fake_dispatch)

    result = asyncio.run(orchestrator.run_scraping_cycle(db, topic_id=seeded_db["topic_a"].id))

    assert result["success"], f"Targeted ingestion failed: {result['errors']}"
    assert result["new_posts_saved"] == 1, "Topic A run must save exactly one matching post"
    assert calls == [(seeded_db["topic_a"].sources[0].id, ["alpha"])], "Only Topic A source and keyword may be evaluated"
    posts = db.query(Post).all()
    assert len(posts) == 1, "Topic B must not produce a post during Topic A ingestion"
    assert posts[0].topic_id == seeded_db["topic_a"].id, "Saved post must carry the triggering topic_id"
    assert posts[0].source_id == seeded_db["topic_a"].sources[0].id, "Saved post must carry Topic A source_id"


def test_ingestion_without_keywords_keeps_all_source_posts(db, seeded_db, monkeypatch):
    db.query(Post).delete()
    db.query(Keyword).filter(Keyword.topic_id == seeded_db["topic_a"].id).delete()
    db.commit()
    orchestrator = ScraperOrchestrator()

    async def fake_scrape(source, keywords):
        return [{
            "external_id": "without-keyword-1",
            "platform": source.platform,
            "author": "fixture",
            "title": "Unrelated headline",
            "content": "This story has no configured keyword.",
            "published_at": datetime.now(timezone.utc),
        }]

    monkeypatch.setattr(orchestrator, "_scrape_source", fake_scrape)
    monkeypatch.setattr(
        "app.services.scraper_orchestrator.dispatch_post_ingested",
        lambda _payload: asyncio.sleep(0, result={"delivered": False, "error": "Webhook URL is not configured"}),
    )

    result = asyncio.run(orchestrator.run_scraping_cycle(db, topic_id=seeded_db["topic_a"].id))

    assert result["success"] is True
    assert result["new_posts_saved"] == 1
    assert db.query(Post).one().content == "This story has no configured keyword."


def test_n8n_payload_contains_topic_context(seeded_db):
    post = seeded_db["topic_a"].posts[0]
    payload = build_n8n_post_payload(post, seeded_db["topic_a"])

    assert payload["topic_id"] == seeded_db["topic_a"].id
    assert payload["topic_title"] == "Topic A"
    assert payload["topic_description"] is None
    assert "Topic A" in payload["ai_prompt"]
    assert payload["post"]["content"] == post.content
