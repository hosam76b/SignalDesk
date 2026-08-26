"""Deterministic Meta Graph API adapter tests."""

import asyncio

from app.services.meta_service import MetaGraphService
from config import settings


def test_meta_service_is_safe_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "meta_access_token", "")
    result = asyncio.run(MetaGraphService().fetch_page_posts("123"))
    assert result["success"] is False
    assert result["posts"] == []


def test_meta_service_normalizes_page_posts(monkeypatch):
    monkeypatch.setattr(settings, "meta_access_token", "meta-token")
    monkeypatch.setattr(settings, "meta_graph_api_version", "v21.0")

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"id": "page_1", "message": "Hello", "created_time": "2026-08-26T10:00:00Z", "permalink_url": "https://facebook.com/post", "from": {"name": "Page"}}]}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, endpoint, params):
            assert endpoint.endswith("/123/posts")
            assert params["access_token"] == "meta-token"
            return Response()

    monkeypatch.setattr("httpx.AsyncClient", lambda **_kwargs: Client())
    result = asyncio.run(MetaGraphService().fetch_page_posts("https://facebook.com/profile.php?id=123"))
    assert result["success"] is True
    assert result["method"] == "meta_graph_api"
    assert result["posts"][0]["author"] == "Page"
    assert result["posts"][0]["platform"] == "facebook"
