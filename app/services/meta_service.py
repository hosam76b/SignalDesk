"""Optional Meta Graph API adapter for approved Facebook Page access."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from config import settings


class MetaGraphService:
    """Fetch Facebook Page posts using a server-side Meta access token."""

    @property
    def is_configured(self) -> bool:
        return bool(settings.meta_access_token)

    async def fetch_page_posts(self, page_id_or_url: str, limit: int = 50) -> dict[str, Any]:
        if not self.is_configured:
            return {"success": False, "posts": [], "error": "Meta Graph API is not configured"}
        parsed = urlsplit(page_id_or_url)
        page_id = parse_qs(parsed.query).get("id", [""])[0] or parsed.path.rstrip("/").rsplit("/", 1)[-1] or page_id_or_url
        endpoint = f"https://graph.facebook.com/{settings.meta_graph_api_version}/{page_id}/posts"
        params = {"access_token": settings.meta_access_token, "fields": "id,message,created_time,permalink_url,from", "limit": min(limit, 100)}
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(endpoint, params=params)
                response.raise_for_status()
                data = response.json()
            return {"success": True, "posts": [self._normalize(item, page_id_or_url) for item in data.get("data", [])], "error": None, "method": "meta_graph_api"}
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            return {"success": False, "posts": [], "error": str(exc), "method": "meta_graph_api"}

    @staticmethod
    def _normalize(item: dict[str, Any], source_url: str) -> dict[str, Any]:
        published = item.get("created_time")
        published_at = datetime.now(timezone.utc) if not published else datetime.fromisoformat(str(published).replace("Z", "+00:00"))
        return {"external_id": str(item.get("id", "")), "platform": "facebook", "author": str((item.get("from") or {}).get("name") or source_url), "title": "", "content": str(item.get("message") or ""), "post_url": item.get("permalink_url") or source_url, "source_url": source_url, "published_at": published_at, "media_urls": []}