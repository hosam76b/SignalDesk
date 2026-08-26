"""Platform registry and routing tests."""

import asyncio

from app.services.scraper_service import APIFY_PLATFORMS, SUPPORTED_PLATFORMS, ScraperService


def test_supported_platform_registry_includes_active_social_platforms():
    assert {"rss", "reddit", "youtube", "facebook", "instagram", "x", "twitter", "tiktok", "threads"} <= SUPPORTED_PLATFORMS
    assert {"facebook", "instagram", "x", "twitter", "tiktok", "threads"} <= APIFY_PLATFORMS


def test_tiktok_and_threads_use_apify_when_configured(monkeypatch):
    service = ScraperService()
    service.apify.api_token = "test-token"
    service.apify.actor_id = "default/actor"
    calls = []

    async def fake_apify(platform, target, actor_input=None, actor_id=None):
        calls.append((platform, target, actor_id))
        return {"success": True, "posts": []}

    monkeypatch.setattr(service.apify, "scrape_social_source", fake_apify)
    for platform in ("instagram", "twitter", "tiktok", "threads"):
        result = asyncio.run(service.scrape_source(platform, "https://example.com/profile", apify_actor_id="custom/actor"))
        assert result["success"] is True
    assert [call[0] for call in calls] == ["instagram", "twitter", "tiktok", "threads"]
    assert all(call[2] == "custom/actor" for call in calls)
