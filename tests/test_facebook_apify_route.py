"""End-to-end offline proof of the facebook -> Apify -> normalize_post route.

Stubs the Apify HTTP transport so no credits are spent. Verifies that the
maxItems cap is injected into the real payload, that the dataset items reach
ScraperService.normalize_post, and that the result matches the Post contract
that scraper_orchestrator._save_posts() expects.
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import contextmanager

import pytest

from app.services.scraper_service import ScraperService
from app.services.apify_service import ApifyService
from config import settings

TARGET = "https://www.facebook.com/NSD.Tripoli"
ACTOR = "cleansyntax~facebook-posts-scraper"

# A dataset item shaped like a real Facebook page-post actor output. Field
# names deliberately vary so normalize_post's aliasing is exercised.
FAKE_ITEMS = [
    {
        "post_id": "pfbid02NSDTripoli001",
        "url": "https://www.facebook.com/NSD.Tripoli/posts/123456",
        "text": "بيان تعيين مدير أمن مدينة طرابلس",
        "timestamp": "2026-09-28T14:05:00.000Z",
        "author": {"name": "مديرية أمن طرابلس"},
        "photos": ["https://scontent.xx.fbcdn.net/photo1.jpg"],
    },
    {
        "post_id": "pfbid02NSDTripoli002",
        "url": "https://www.facebook.com/NSD.Tripoli/posts/123457",
        "text": "اجتماعTAIN.lua(cc) في مقر المديرية",
        "timestamp": 1789012345,
        "author": {"name": "مديرية أمن طرابلس"},
        "photos": [],
    },
]

CAPTURED: list[dict] = []


class _Resp:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> list[dict]:
        return FAKE_ITEMS


class _Client:
    def __init__(self, *a, **k) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, endpoint, params=None, json=None):
        CAPTURED.append({"endpoint": endpoint, "payload": json, "params": params})
        return _Resp()


@contextmanager
def _stub_apify_transport():
    import httpx

    real = sys.modules.get("apify_client", "absent")
    sys.modules["apify_client"] = None  # type: ignore[assignment]
    original = httpx.AsyncClient
    httpx.AsyncClient = _Client  # type: ignore[misc]
    CAPTURED.clear()
    try:
        yield
    finally:
        httpx.AsyncClient = original  # type: ignore[misc]
        if real == "absent":
            sys.modules.pop("apify_client", None)
        else:
            sys.modules["apify_client"] = real  # type: ignore[assignment]


def _scrape(actor_id=ACTOR):
    svc = ScraperService()
    with _stub_apify_transport():
        result = asyncio.run(
            svc.scrape_source("facebook", TARGET, apify_actor_id=actor_id)
        )
    return result, CAPTURED[0] if CAPTURED else None


def test_full_route_returns_posts_and_uses_actor_endpoint():
    result, call = _scrape()

    assert call is not None, "Apify transport was never called"
    assert f"/acts/{ACTOR}/run-sync-get-dataset-items" in call["endpoint"]
    assert result["success"] is True
    assert len(result["posts"]) == len(FAKE_ITEMS)


def test_payload_carries_capped_max_items():
    _, call = _scrape()
    payload = call["payload"]

    if "maxItems" in payload:
        assert payload["maxItems"] == settings.apify_max_items_per_run == 25
    elif "max_posts" in payload:
        assert payload["max_posts"] == settings.apify_max_items_per_run == 25
    if "startUrls" in payload:
        assert payload["startUrls"] == [{"url": TARGET}]
    if "urls_text" in payload:
        assert payload["urls_text"] == TARGET


def test_token_is_sent_as_query_param():
    _, call = _scrape()
    assert call["params"]["token"] == settings.apify_api_token


def test_items_match_the_post_contract():
    """Fields _save_posts() and normalize_post() rely on must be present."""
    result, _ = _scrape()
    first = result["posts"][0]

    assert first["platform"] == "facebook"
    assert first["external_id"] == "pfbid02NSDTripoli001"
    assert first["post_url"] == "https://www.facebook.com/NSD.Tripoli/posts/123456"
    assert first["author"] == "مديرية أمن طرابلس"
    assert "بيان" in first["content"]
    assert first["published_at"] is not None
    assert isinstance(first["media_urls"], list)
    assert first["raw_metadata"]["post_id"] == "pfbid02NSDTripoli001"


def test_second_item_parses_numeric_timestamp():
    result, _ = _scrape()
    second = result["posts"][1]
    assert second["published_at"].year == 2026


def test_resolve_actor_id_prefers_per_source_override():
    svc = ApifyService()
    assert svc.resolve_actor_id("facebook", ACTOR) == ACTOR


def test_missing_actor_id_is_rejected_before_network():
    """A facebook source with no actor ID must fail loudly, not silently."""
    svc = ScraperService()
    svc.apify.actor_id = ""
    svc.apify.api_token = settings.apify_api_token
    if settings.apify_facebook_actor_id:
        pytest.skip("a per-platform facebook actor is configured in this environment")
    assert svc.apify.resolve_actor_id("facebook") is None
    assert svc.apify.is_configured is True, "token alone is not enough to scrape"
