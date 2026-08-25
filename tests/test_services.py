"""Deterministic unit tests for external-service adapters and orchestration."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from app.core.security import create_access_token, decode_token
from app.services.apify_service import ApifyService
from app.services.playwright_service import PlaywrightService
from app.services.scraper_orchestrator import ScraperOrchestrator
from app.services.scraper_service import ScraperService
from app.services.rss_service import RSSService
from app.services.youtube_service import YouTubeService


def test_security_token_round_trip():
    token = create_access_token({"sub": "42", "role": "super_admin"})
    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "super_admin"


def test_apify_unconfigured_is_safe(monkeypatch):
    service = ApifyService()
    service.api_token = ""
    result = asyncio.run(service.run_actor("facebook", "https://example.com"))
    assert result == {"success": False, "posts": [], "error": "Apify is not configured"}


def test_apify_http_fallback_normalizes_items(monkeypatch):
    service = ApifyService()
    service.api_token = "token"
    service.actor_id = "actor"

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"id": "1", "text": "sample"}]

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setitem(__import__("sys").modules, "apify_client", None)
    monkeypatch.setattr("httpx.AsyncClient", lambda **_kwargs: FakeClient())
    result = asyncio.run(service.run_actor("facebook", "https://example.com"))
    assert result["success"] is True
    assert result["posts"][0]["external_id"] == "1"


def test_scraper_normalization_and_keyword_helpers():
    normalized = ScraperService.normalize_post(
        {"text": "  Alpha  ", "thumbnail": "https://image", "author": "tester", "created_at": "2026-01-01T00:00:00Z"},
        "rss",
        "https://example.com",
    )
    assert normalized["content"] == "Alpha"
    assert normalized["media_urls"] == ["https://image"]
    assert normalized["published_at"].year == 2026
    assert ScraperOrchestrator._matches_keywords(normalized, ["alpha"])
    assert not ScraperOrchestrator._matches_keywords(normalized, ["bravo"])


def test_scraper_service_unsupported_and_apify_route(monkeypatch):
    service = ScraperService()
    result = asyncio.run(service.scrape_source("unknown", "target"))
    assert result["success"] is False

    async def fake_apify(*_args, **_kwargs):
        return {"success": True, "posts": []}

    service.apify.api_token = "token"
    service.apify.actor_id = "actor"
    monkeypatch.setattr(service.apify, "scrape_social_source", fake_apify)
    result = asyncio.run(service.scrape_source("facebook", "https://facebook.com/page", apify_actor_id="custom/actor"))
    assert result["success"] is True


def test_rss_helpers_and_feed_failure(monkeypatch):
    service = RSSService()
    entry = {"id": "rss-1", "title": "Title", "summary": "<b>Body</b>", "link": "https://example.com/1"}
    extracted = service._extract_posts({"entries": [entry]})
    assert extracted[0]["content"] == "Body"
    assert service._strip_html("<p>clean</p>") == "clean"
    assert service._get_post_id({"title": "fallback"}).startswith("rss_")

    class FailedResponse:
        content = b""
        encoding = "utf-8"

        def raise_for_status(self):
            raise RuntimeError("network down")

    monkeypatch.setattr("httpx.get", lambda *_args, **_kwargs: FailedResponse())
    result = service.parse_feed("https://example.com/feed")
    assert result["success"] is False
    assert result["posts"] == []


def test_youtube_service_search_and_transcript(monkeypatch):
    service = YouTubeService.__new__(YouTubeService)

    class SearchRequest:
        def list(self, **_kwargs):
            return self

        def execute(self):
            return {"items": [{"id": {"videoId": "vid-1"}, "snippet": {"title": "Video", "description": "Desc", "channelTitle": "Channel", "publishedAt": "2026-01-01T00:00:00Z"}}]}

    class FakeYoutube:
        def search(self):
            return SearchRequest()

    service.youtube = FakeYoutube()
    monkeypatch.setattr(service, "get_transcript", lambda _video_id: {"success": True, "transcript": "Transcript", "language": "en"})
    result = service.search_videos("alpha", max_results=1)
    assert result["success"] is True
    assert result["videos"][0]["external_id"] == "vid-1"
    assert service._parse_date(None).tzinfo == timezone.utc


def test_playwright_not_initialized_and_close():
    service = PlaywrightService()
    result = asyncio.run(service.scrape_page("https://example.com"))
    assert result["success"] is False
    result = asyncio.run(service.scrape_social_page("https://example.com", "facebook"))
    assert result["success"] is False
    asyncio.run(service.close())


def test_orchestrator_all_topics_runs_each_topic(db, seeded_db, monkeypatch):
    orchestrator = ScraperOrchestrator()
    seen = []

    async def fake_scrape(source, keywords):
        seen.append((source.topic_id, tuple(keywords)))
        return []

    monkeypatch.setattr(orchestrator, "_scrape_source", fake_scrape)
    result = asyncio.run(orchestrator.run_scraping_cycle(db))
    assert result["total_sources"] == 2
    assert {topic_id for topic_id, _keywords in seen} == {seeded_db["topic_a"].id, seeded_db["topic_b"].id}
