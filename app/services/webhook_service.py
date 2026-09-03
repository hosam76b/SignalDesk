"""Outbound webhook delivery with DB-backed subscriptions, HMAC signing, and delivery logs.

Integrates SignalDesk with external automation tools (n8n, Zapier, Make, ...)
by delivering signed JSON events to administrator-managed webhook endpoints.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.webhook import Webhook, WebhookDelivery
from config import settings

logger = logging.getLogger(__name__)

WEBHOOK_EVENT_POST_INGESTED = "post_ingested"
WEBHOOK_EVENT_ALERT_TRIGGERED = "alert_triggered"
WEBHOOK_EVENT_REPORT_READY = "report_ready"
WEBHOOK_EVENT_ANALYSIS_COMPLETED = "analysis_completed"

WEBHOOK_EVENTS: tuple[str, ...] = (
    WEBHOOK_EVENT_POST_INGESTED,
    WEBHOOK_EVENT_ALERT_TRIGGERED,
    WEBHOOK_EVENT_REPORT_READY,
    WEBHOOK_EVENT_ANALYSIS_COMPLETED,
)

REQUEST_TIMEOUT = 15.0


def normalize_events(events: list[str] | None) -> list[str]:
    """Validate and deduplicate subscribed event names."""
    if not events:
        return [WEBHOOK_EVENT_POST_INGESTED]
    normalized: list[str] = []
    for event in events:
        name = str(event).strip()
        if name not in WEBHOOK_EVENTS:
            raise ValueError(
                f"Unsupported webhook event: {name}. Supported events: {', '.join(WEBHOOK_EVENTS)}"
            )
        if name not in normalized:
            normalized.append(name)
    return normalized


def get_subscribed_webhooks(db: Session, event: str) -> list[Webhook]:
    """Return active webhooks subscribed to the given event."""
    webhooks = db.query(Webhook).filter(Webhook.is_active.is_(True)).all()
    return [webhook for webhook in webhooks if event in (webhook.events or [])]


def sign_payload(secret: str, body: bytes) -> str:
    """Compute the HMAC-SHA256 hex signature for a raw request body."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def build_headers(webhook: Webhook, event: str, delivery_uid: str, body: bytes) -> dict[str, str]:
    """Build delivery headers, adding the HMAC signature when a secret is set."""
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SignalDesk-Webhook/1.0",
        "X-Webhook-Event": event,
        "X-Webhook-Delivery": delivery_uid,
    }
    if webhook.secret:
        headers["X-Webhook-Signature"] = f"sha256={sign_payload(webhook.secret, body)}"
    return headers


def _build_envelope(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Wrap an event payload in the standard delivery envelope."""
    return {
        "event": event,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "data": _json_safe(payload),
    }


def _record_delivery(db: Session, webhook: Webhook, event: str, envelope: dict[str, Any], result: dict[str, Any]) -> None:
    """Persist a delivery attempt without ever breaking the caller's flow."""
    try:
        delivery = WebhookDelivery(
            webhook_id=webhook.id,
            event=event,
            payload=envelope,
            status_code=result.get("status_code"),
            success=bool(result.get("delivered")),
            error=result.get("error") or None,
            duration_ms=result.get("duration_ms"),
        )
        db.add(delivery)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to record webhook delivery for webhook %s", webhook.id)


def _format_response_error(response: httpx.Response, url: str) -> str:
    try:
        detail = response.json()
    except ValueError:
        detail = response.text.strip()

    if response.status_code == 404 and "/webhook-test/" in url:
        logger.warning(
            "n8n test webhook is unavailable: %s. Start 'Listen for test event', "
            "or activate the workflow and use its /webhook/ production URL.",
            url,
        )

    if isinstance(detail, dict):
        message = detail.get("message") or detail.get("error") or response.reason_phrase
        hint = detail.get("hint")
        return f"Webhook endpoint returned {response.status_code}: {message}" + (f" Hint: {hint}" if hint else "")
    return f"Webhook endpoint returned {response.status_code}: {detail or response.reason_phrase}"


async def _deliver_async(client: httpx.AsyncClient, webhook: Webhook, event: str, envelope: dict[str, Any]) -> dict[str, Any]:
    """Deliver one envelope to one webhook using an async client."""
    body = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
    headers = build_headers(webhook, event, uuid.uuid4().hex, body)
    started = time.perf_counter()
    try:
        response = await client.post(webhook.url, content=body, headers=headers)
        duration_ms = int((time.perf_counter() - started) * 1000)
        if response.is_success:
            return {"success": True, "delivered": True, "status_code": response.status_code, "duration_ms": duration_ms}
        error = _format_response_error(response, webhook.url)
        logger.warning("Webhook rejected by %s: %s", webhook.url, error)
        return {"success": False, "delivered": False, "status_code": response.status_code, "duration_ms": duration_ms, "error": error}
    except httpx.HTTPError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.warning("Webhook delivery to %s failed: %s", webhook.url, exc)
        return {"success": False, "delivered": False, "duration_ms": duration_ms, "error": str(exc)}


def _deliver_sync(client: httpx.Client, webhook: Webhook, event: str, envelope: dict[str, Any]) -> dict[str, Any]:
    """Deliver one envelope to one webhook using a blocking client."""
    body = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
    headers = build_headers(webhook, event, uuid.uuid4().hex, body)
    started = time.perf_counter()
    try:
        response = client.post(webhook.url, content=body, headers=headers)
        duration_ms = int((time.perf_counter() - started) * 1000)
        if response.is_success:
            return {"success": True, "delivered": True, "status_code": response.status_code, "duration_ms": duration_ms}
        error = _format_response_error(response, webhook.url)
        logger.warning("Webhook rejected by %s: %s", webhook.url, error)
        return {"success": False, "delivered": False, "status_code": response.status_code, "duration_ms": duration_ms, "error": error}
    except httpx.HTTPError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.warning("Webhook delivery to %s failed: %s", webhook.url, exc)
        return {"success": False, "delivered": False, "duration_ms": duration_ms, "error": str(exc)}


def _summarize(event: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    delivered = sum(1 for result in results if result["delivered"])
    return {
        "success": all(result["delivered"] for result in results) if results else True,
        "event": event,
        "attempted": len(results),
        "delivered": delivered,
        "results": results,
    }


async def dispatch_event(db: Session, event: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Deliver an event to every active subscribed webhook (async contexts)."""
    envelope = _build_envelope(event, payload)
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for webhook in get_subscribed_webhooks(db, event):
            result = await _deliver_async(client, webhook, event, envelope)
            result["webhook_id"] = webhook.id
            result["webhook_name"] = webhook.name
            _record_delivery(db, webhook, event, envelope, result)
            results.append(result)
    return _summarize(event, results)


def dispatch_event_blocking(db: Session, event: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Deliver an event to every active subscribed webhook (sync contexts)."""
    envelope = _build_envelope(event, payload)
    results: list[dict[str, Any]] = []
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        for webhook in get_subscribed_webhooks(db, event):
            result = _deliver_sync(client, webhook, event, envelope)
            result["webhook_id"] = webhook.id
            result["webhook_name"] = webhook.name
            _record_delivery(db, webhook, event, envelope, result)
            results.append(result)
    return _summarize(event, results)


def dispatch_event_background(event: str, payload: dict[str, Any]) -> None:
    """Blocking dispatch on a fresh session; safe for FastAPI BackgroundTasks."""
    db = SessionLocal()
    try:
        dispatch_event_blocking(db, event, payload)
    except Exception:
        logger.exception("Background webhook dispatch failed for event %s", event)
    finally:
        db.close()


async def send_test_event(db: Session, webhook: Webhook, triggered_by: str) -> dict[str, Any]:
    """Send a signed test event to a single webhook and record the delivery."""
    envelope = _build_envelope("test", {
        "message": "SignalDesk webhook test delivery",
        "triggered_by": triggered_by,
    })
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        result = await _deliver_async(client, webhook, "test", envelope)
    result["webhook_id"] = webhook.id
    result["webhook_name"] = webhook.name
    _record_delivery(db, webhook, "test", envelope, result)
    return result


async def dispatch_post_ingested(payload: dict[str, Any], db: Session | None = None) -> dict[str, Any]:
    """Forward an ingestion batch to DB webhook subscriptions and the legacy env-configured URL."""
    combined: dict[str, Any] = {"success": True, "delivered": False, "status_code": None, "error": None}
    attempted = False

    if db is not None:
        dispatch_result = await dispatch_event(db, WEBHOOK_EVENT_POST_INGESTED, payload)
        attempted = attempted or dispatch_result["attempted"] > 0
        combined["subscriptions"] = dispatch_result["attempted"]
        if dispatch_result["delivered"]:
            combined["delivered"] = True
        failed = next((r for r in dispatch_result["results"] if not r["delivered"]), None)
        if failed is not None:
            combined.update({
                "success": False,
                "status_code": failed.get("status_code"),
                "error": failed.get("error"),
            })

    url = settings.post_ingested_webhook_url
    if url:
        attempted = True
        legacy_result = await _dispatch_legacy_url(url, payload)
        if legacy_result.get("delivered"):
            combined["delivered"] = True
            combined["status_code"] = legacy_result.get("status_code")
        else:
            combined.update({
                "success": False,
                "status_code": legacy_result.get("status_code"),
                "error": legacy_result.get("error"),
            })

    if not attempted:
        return {"success": False, "delivered": False, "error": "Webhook URL is not configured"}
    return combined


async def _dispatch_legacy_url(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST to the legacy env-configured webhook URL (backward compatibility)."""
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(url, json=_json_safe(payload))
            response.raise_for_status()
        return {"success": True, "delivered": True, "status_code": response.status_code}
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "delivered": False,
            "status_code": exc.response.status_code,
            "error": _format_response_error(exc.response, url),
        }
    except httpx.HTTPError as exc:
        logger.warning("Post-ingested webhook delivery failed: %s", exc)
        return {"success": False, "delivered": False, "error": str(exc)}


def _json_safe(value: Any) -> Any:
    """Convert datetime and nested values into JSON-compatible values."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
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
