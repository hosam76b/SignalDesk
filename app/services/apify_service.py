"""Optional Apify actor integration for social-media ingestion."""

from __future__ import annotations

import json
import logging
import asyncio
from typing import Any, Mapping

import httpx

from config import settings
logger = logging.getLogger(__name__)

# The SDK raises ApifyApiError on a rejected run (bad input, missing billing
# method, actor not found). That is an ordinary, expected ingestion failure --
# one misconfigured actor must not propagate out of the scheduler and abort the
# scrape cycle -- so it is caught alongside the transport errors. The client is
# optional, hence the guarded import.
try:  # pragma: no cover - depends on apify-client being installed
    from apify_client.errors import ApifyApiError as _ApifyApiError

    _TRANSPORT_ERRORS: tuple[type[BaseException], ...] = (
        httpx.HTTPError,
        ValueError,
        KeyError,
        ImportError,
        _ApifyApiError,
    )
except ImportError:  # pragma: no cover - HTTP fallback only
    _TRANSPORT_ERRORS = (httpx.HTTPError, ValueError, KeyError, ImportError)


class ApifyService:
    """Run configured Apify actors and normalize their dataset items."""

    PLATFORM_ACTOR_FIELDS = {
        "facebook": "apify_facebook_actor_id",
        "instagram": "apify_instagram_actor_id",
        "x": "apify_x_actor_id",
        "twitter": "apify_x_actor_id",
        "tiktok": "apify_tiktok_actor_id",
        "threads": "apify_threads_actor_id",
    }

    def __init__(self) -> None:
        self.api_token = settings.apify_api_token
        self.actor_id = settings.apify_actor_id or ""
        self.base_url = "https://api.apify.com/v2"

    def resolve_actor_id(self, platform: str, actor_id: str | None = None) -> str | None:
        """Return the best actor ID for the platform, preferring per-source overrides."""
        if actor_id:
            return actor_id

        field_name = self.PLATFORM_ACTOR_FIELDS.get(platform.lower(), "apify_actor_id")
        platform_actor = getattr(settings, field_name, None) or ""
        if platform_actor:
            return platform_actor
        return self.actor_id or None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_token)

    def _build_payload(
        self,
        source_url: str,
        actor_input: Mapping[str, Any] | None,
        platform: str = "",
    ) -> dict[str, Any]:
        """Build the actor input for a source URL.

        Apify actors do not share an input schema. Official actors
        (``apify/*``) take ``startUrls`` and cap with ``maxItems``; community
        actors commonly take a different ``endpoint`` selector plus their own
        URL field and their own cap key (for example ``max_posts``). Sending
        the official shape to such an actor is rejected outright with
        ``Input is not valid``, so the shape is chosen per actor and the item
        cap is applied to whichever key that actor understands.

        A caller-supplied value always wins, so an explicit limit is never
        overridden by the configured default.
        """
        max_items = getattr(settings, "apify_max_items_per_run", 25)
        custom = (actor_input or {}).get("template")
        if custom is None:
            # Fall back to the per-platform template in settings so the
            # operator configures it once instead of at every call site.
            custom = getattr(settings, f"apify_{platform}_actor_input", "") or ""

        if isinstance(custom, str):
            custom = custom.strip()

        if custom:
            # A template-driven actor: substitute the URL and the item cap
            # into the keys the template declares, then merge the caller's
            # own fields over it.
            rendered = json.loads(
                custom.replace("{url}", source_url).replace("{max_items}", str(max_items))
            )
            if not isinstance(rendered, dict):
                raise ValueError("Apify actor input template must be a JSON object")
            payload = {k: v for k, v in (actor_input or {}).items() if k != "template"}
            # The template supplies the shape; the caller's own fields win, so
            # an explicit per-call limit is never overwritten by the configured
            # default.
            payload.update({k: v for k, v in rendered.items() if k not in payload})
            return payload

        payload = dict(actor_input or {})
        payload.setdefault("startUrls", [{"url": source_url}])
        # Official actor shape. Only the key that shape declares is set: an
        # actor validates its input strictly and rejects unknown fields, so
        # sending several spellings of the same cap would break this path
        # rather than make it more portable. Community actors get their own
        # key via the template above.
        #
        # Cap dataset size. Apify charges per item and returns the whole
        # dataset before we get to normalize and de-duplicate it, so an
        # unbounded actor run bills first and trims later.
        if "maxItems" not in payload:
            payload["maxItems"] = max_items
        return payload

    async def run_actor(
        self,
        platform: str,
        source_url: str,
        actor_input: Mapping[str, Any] | None = None,
        timeout: float = 120.0,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Run an actor synchronously and return normalized posts."""
        resolved_actor_id = self.resolve_actor_id(platform, actor_id)
        if not self.is_configured or not resolved_actor_id:
            return {"success": False, "posts": [], "error": "Apify is not configured"}

        payload = self._build_payload(source_url, actor_input, platform)
        try:
            try:
                from apify_client import ApifyClient
            except ImportError:
                logger.warning("apify-client is unavailable; using Apify HTTP fallback")
                endpoint = f"{self.base_url}/acts/{resolved_actor_id}/run-sync-get-dataset-items"
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(endpoint, params={"token": self.api_token}, json=payload)
                    response.raise_for_status()
                    data = response.json()
            else:
                def run_actor() -> list[dict[str, Any]]:
                    client = ApifyClient(self.api_token)
                    run = client.actor(resolved_actor_id).call(run_input=payload)
                    dataset_id = (
                        getattr(run, "default_dataset_id", None)
                        or getattr(run, "defaultDatasetId", None)
                        or (run.get("defaultDatasetId") if isinstance(run, Mapping) else None)
                    )
                    if not dataset_id:
                        raise ValueError("Apify run did not return a dataset ID")
                    return list(client.dataset(dataset_id).iterate_items())

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
        except _TRANSPORT_ERRORS as exc:
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
