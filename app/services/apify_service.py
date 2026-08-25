"""Optional Apify actor integration for social-media ingestion."""

from __future__ import annotations

import logging
import asyncio
from typing import Any, Mapping

import httpx

from config import settings
logger = logging.getLogger(__name__)


class ApifyService:
    """Run configured Apify actors and normalize their dataset items."""

    def __init__(self) -> None:
        self.api_token = settings.apify_api_token
        self.actor_id = settings.apify_actor_id or "apify/facebook-posts-scraper"
        self.base_url = "https://api.apify.com/v2"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_token and self.actor_id)

    async def run_actor(
        self,
        platform: str,
        source_url: str,
        actor_input: Mapping[str, Any] | None = None,
        timeout: float = 120.0,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Run an actor synchronously and return normalized posts."""
        if not self.is_configured:
            return {"success": False, "posts": [], "error": "Apify is not configured"}

        payload = dict(actor_input or {})
        payload.setdefault("startUrls", [{"url": source_url}])
        try:
            try:
                from apify_client import ApifyClient
            except ImportError:
                logger.warning("apify-client is unavailable; using Apify HTTP fallback")
                endpoint = f"{self.base_url}/acts/{actor_id or self.actor_id}/run-sync-get-dataset-items"
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(endpoint, params={"token": self.api_token}, json=payload)
                    response.raise_for_status()
                    data = response.json()
            else:
                def run_actor() -> list[dict[str, Any]]:
                    client = ApifyClient(self.api_token)
                    run = client.actor(actor_id or self.actor_id).call(run_input=payload)
                    return list(client.dataset(run["defaultDatasetId"]).iterate_items())

                data = await asyncio.to_thread(run_actor)
            if not isinstance(data, list):
                raise ValueError("Apify response must be a dataset item list")
            from app.services.scraper_service import ScraperService

            posts = []
            for item in data:
                if not isinstance(item, Mapping):
                    continue
                try:
                    posts.append(ScraperService.normalize_post(item, platform, source_url))
                except Exception as exc:
                    logger.warning("Skipping malformed Apify item from %s: %s", source_url, exc)
            return {"success": True, "posts": posts, "error": None}
        except (httpx.HTTPError, ValueError, KeyError, ImportError) as exc:
            logger.exception("Apify ingestion failed for %s (%s): %s", source_url, platform, exc)
            return {"success": False, "posts": [], "error": str(exc)}

    async def scrape_social_source(
        self,
        platform: str,
        source_url: str,
        actor_input: Mapping[str, Any] | None = None,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Convenience wrapper for Facebook, X, and Instagram sources."""
        return await self.run_actor(platform, source_url, actor_input, actor_id=actor_id)
