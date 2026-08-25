"""Outbound webhook delivery for newly ingested posts."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)


async def dispatch_post_ingested(payload: dict[str, Any]) -> dict[str, Any]:
    """POST an ingestion batch to the configured automation webhook."""
    url = settings.post_ingested_webhook_url
    if not url:
        return {"success": False, "delivered": False, "error": "Webhook URL is not configured"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=_json_safe(payload))
            response.raise_for_status()
        return {"success": True, "delivered": True, "status_code": response.status_code}
    except httpx.HTTPError as exc:
        logger.exception("Post-ingested webhook delivery failed: %s", exc)
        return {"success": False, "delivered": False, "error": str(exc)}


def _json_safe(value: Any) -> Any:
    """Convert datetime and nested values into JSON-compatible values."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def build_n8n_post_payload(post: Any, topic: Any) -> dict[str, Any]:
    """Build a topic-aware payload for n8n and downstream LLM processing."""
    return {
        "event": "post_ingested",
        "topic_id": topic.id,
        "topic_title": topic.title,
        "topic_description": topic.description,
        "ai_prompt": (
            f"Analyze this post in the context of [Topic Title: {topic.title}]. "
            f"Topic description: {topic.description or 'No description provided'}."
        ),
        "post": _json_safe({
            "id": post.id,
            "source_id": post.source_id,
            "platform": post.platform,
            "title": post.title,
            "content": post.content,
            "author": post.author,
            "published_at": post.published_at,
        }),
    }
