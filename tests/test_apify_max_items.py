"""Verify the Apify maxItems cap is injected and respects a caller's limit."""

from __future__ import annotations

import asyncio
import sys
from contextlib import contextmanager

import pytest

from app.services.apify_service import ApifyService
from config import settings


CAPTURED: list[dict] = []


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> list[dict]:
        return []


class _FakeClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def post(self, endpoint, params=None, json=None):
        CAPTURED.append({"endpoint": endpoint, "payload": json})
        return _FakeResponse()


@contextmanager
def _http_only():
    """Patch httpx and hide apify_client so run_actor takes the HTTP path."""
    import httpx

    real = sys.modules.get("apify_client", "absent")
    sys.modules["apify_client"] = None  # type: ignore[assignment]
    original = httpx.AsyncClient
    httpx.AsyncClient = _FakeClient  # type: ignore[misc]
    try:
        yield
    finally:
        httpx.AsyncClient = original  # type: ignore[misc]
        if real == "absent":
            sys.modules.pop("apify_client", None)
        else:
            sys.modules["apify_client"] = real  # type: ignore[assignment]


# A real actor ID must be resolvable, otherwise run_actor short-circuits with
# "Apify is not configured" before it ever builds a payload.
ACTOR_ID = "owner/test-actor~1.0"


def _run(actor_input=None) -> dict:
    CAPTURED.clear()
    with _http_only():
        asyncio.run(
            ApifyService().run_actor(
                "x", "https://x.com/user", actor_input=actor_input, actor_id=ACTOR_ID
            )
        )
    return CAPTURED[0]["payload"]


def test_max_items_defaults_to_setting() -> None:
    payload = _run()
    assert payload["maxItems"] == 25
    assert payload["startUrls"] == [{"url": "https://x.com/user"}]


def test_caller_supplied_max_items_wins() -> None:
    assert _run(actor_input={"maxItems": 5})["maxItems"] == 5


def test_caller_input_is_not_mutated() -> None:
    actor_input = {"startUrls": [{"url": "https://x.com/other"}]}
    _run(actor_input=actor_input)
    assert "maxItems" not in actor_input


def test_community_template_shape_is_used_when_configured():
    """A configured template must replace the official shape entirely.

    scraper_one/facebook-posts-scraper rejects startUrls and maxItems; it
    requires pageUrls plus resultsLimit. Sending the official shape raises
    'Input is not valid' and loses the whole batch.
    """
    svc = ApifyService()
    payload = svc._build_payload(
        "https://www.facebook.com/NSD.Tripoli",
        {"template": '{"pageUrls": ["{url}"], "resultsLimit": {max_items}}'},
        "facebook",
    )
    assert payload == {
        "pageUrls": ["https://www.facebook.com/NSD.Tripoli"],
        "resultsLimit": settings.apify_max_items_per_run,
    }
    # The official keys must not leak into a template-driven payload.
    assert "startUrls" not in payload
    assert "maxItems" not in payload


def test_cap_key_never_mixed_across_actor_shapes():
    """A strict actor rejects unknown fields, so only its own cap key ships."""
    svc = ApifyService()
    official = svc._build_payload("https://x.com/u", None, "twitter")
    assert official["maxItems"] == settings.apify_max_items_per_run
    for foreign in ("resultsLimit", "max_posts"):
        assert foreign not in official


def test_template_respects_caller_supplied_limit():
    svc = ApifyService()
    payload = svc._build_payload(
        "https://www.facebook.com/NSD.Tripoli",
        {"template": '{"pageUrls": ["{url}"], "resultsLimit": {max_items}}', "resultsLimit": 3},
        "facebook",
    )
    assert payload["resultsLimit"] == 3


def test_all_platform_actor_fields_still_resolve() -> None:
    svc = ApifyService()
    expected = {
        "facebook": "apify_facebook_actor_id",
        "instagram": "apify_instagram_actor_id",
        "x": "apify_x_actor_id",
        "twitter": "apify_x_actor_id",
        "tiktok": "apify_tiktok_actor_id",
        "threads": "apify_threads_actor_id",
    }
    assert svc.PLATFORM_ACTOR_FIELDS == expected
    # Per-source override still beats the platform default.
    assert svc.resolve_actor_id("x", "owner/custom~1.0") == "owner/custom~1.0"
    # No actor IDs are configured for the platforms under test, so they fall
    # through to the generic default and yield None rather than a bogus ID.
    # That is the signal callers use to report "Apify is not configured".
    for platform in ("facebook", "instagram", "x", "tiktok", "threads"):
        if getattr(settings, f"apify_{platform}_actor_id", ""):
            continue
        assert svc.resolve_actor_id(platform) is None
