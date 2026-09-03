"""Webhook management endpoints for external automation (n8n, Zapier, Make, ...)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.deps import get_current_admin_user, get_current_user
from app.db.session import get_db
from app.models.post import Post
from app.models.user import User
from app.models.webhook import Webhook, WebhookDelivery
from app.services.audit_service import record_audit
from app.services.webhook_service import (
    WEBHOOK_EVENTS,
    dispatch_post_ingested,
    normalize_events,
    send_test_event,
)

router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])

EVENT_DESCRIPTIONS = {
    "post_ingested": "Fired when new posts are ingested from monitored sources.",
    "alert_triggered": "Fired when a new high/critical topic alert is detected.",
    "report_ready": "Fired when an executive PDF report is generated.",
    "analysis_completed": "Fired when the AI analysis batch finishes processing posts.",
}


def _validate_webhook_url(value: str) -> str:
    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Webhook URL must be a valid http(s) URL")
    return url


class WebhookCreate(BaseModel):
    """Payload for creating a webhook subscription."""

    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=8, max_length=1000)
    secret: str = Field(default="", max_length=255)
    events: list[str] = Field(default_factory=lambda: ["post_ingested"])
    is_active: bool = True

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _validate_webhook_url(value)

    @field_validator("events")
    @classmethod
    def validate_events(cls, value: list[str]) -> list[str]:
        return normalize_events(value)


class WebhookUpdate(BaseModel):
    """Payload for updating a webhook subscription (partial)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    url: str | None = Field(default=None, min_length=8, max_length=1000)
    secret: str | None = Field(default=None, max_length=255)
    events: list[str] | None = None
    is_active: bool | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_webhook_url(value)

    @field_validator("events")
    @classmethod
    def validate_events(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return normalize_events(value)


class WebhookOut(BaseModel):
    """Public representation of a webhook subscription (secret is never exposed)."""

    id: int
    name: str
    url: str
    has_secret: bool
    events: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_delivery_at: datetime | None = None
    last_delivery_success: bool | None = None


class DeliveryOut(BaseModel):
    """A single webhook delivery attempt."""

    id: int
    webhook_id: int
    event: str
    status_code: int | None = None
    success: bool
    error: str | None = None
    duration_ms: int | None = None
    created_at: datetime


class PostIngestedRequest(BaseModel):
    """Optional explicit batch payload for webhook delivery."""

    post_ids: list[int] = Field(default_factory=list, max_length=500)


class WebhookResponse(BaseModel):
    """Webhook delivery result."""

    success: bool
    delivered: bool
    status_code: int | None = None
    error: str | None = None


def _get_webhook_or_404(db: Session, webhook_id: int) -> Webhook:
    webhook = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if webhook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    return webhook


def _serialize_webhook(db: Session, webhook: Webhook) -> WebhookOut:
    last_delivery = (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.webhook_id == webhook.id)
        .order_by(WebhookDelivery.id.desc())
        .first()
    )
    return WebhookOut(
        id=webhook.id,
        name=webhook.name,
        url=webhook.url,
        has_secret=bool(webhook.secret),
        events=list(webhook.events or []),
        is_active=bool(webhook.is_active),
        created_at=webhook.created_at,
        updated_at=webhook.updated_at,
        last_delivery_at=last_delivery.created_at if last_delivery else None,
        last_delivery_success=last_delivery.success if last_delivery else None,
    )


@router.get("/events")
def list_webhook_events(_: User = Depends(get_current_admin_user)) -> dict[str, Any]:
    """List the supported webhook event types."""
    return {
        "events": [
            {"name": name, "description": EVENT_DESCRIPTIONS.get(name, "")}
            for name in WEBHOOK_EVENTS
        ]
    }


@router.get("", response_model=list[WebhookOut])
def list_webhooks(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
) -> list[WebhookOut]:
    """List all configured webhook subscriptions (admin only)."""
    webhooks = db.query(Webhook).order_by(Webhook.id.asc()).all()
    return [_serialize_webhook(db, webhook) for webhook in webhooks]


@router.post("", response_model=WebhookOut, status_code=status.HTTP_201_CREATED)
def create_webhook(
    payload: WebhookCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> WebhookOut:
    """Create a new webhook subscription (admin only)."""
    webhook = Webhook(
        name=payload.name.strip(),
        url=payload.url,
        secret=payload.secret or "",
        events=payload.events,
        is_active=payload.is_active,
        created_by_id=current_user.id,
    )
    db.add(webhook)
    record_audit(
        db,
        user_id=current_user.id,
        action="webhook_created",
        entity_type="webhook",
        details={"name": webhook.name, "url": webhook.url, "events": webhook.events},
    )
    db.commit()
    db.refresh(webhook)
    return _serialize_webhook(db, webhook)


@router.get("/{webhook_id}", response_model=WebhookOut)
def get_webhook(
    webhook_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
) -> WebhookOut:
    """Retrieve a single webhook subscription (admin only)."""
    return _serialize_webhook(db, _get_webhook_or_404(db, webhook_id))


@router.patch("/{webhook_id}", response_model=WebhookOut)
def update_webhook(
    webhook_id: int,
    payload: WebhookUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> WebhookOut:
    """Update a webhook subscription (admin only). Secret is kept unless explicitly sent."""
    webhook = _get_webhook_or_404(db, webhook_id)
    provided = payload.model_fields_set

    if "name" in provided and payload.name is not None:
        webhook.name = payload.name.strip()
    if "url" in provided and payload.url is not None:
        webhook.url = payload.url
    if "secret" in provided and payload.secret is not None:
        webhook.secret = payload.secret
    if "events" in provided and payload.events is not None:
        webhook.events = payload.events
    if "is_active" in provided and payload.is_active is not None:
        webhook.is_active = payload.is_active
    webhook.updated_at = datetime.now(timezone.utc)

    record_audit(
        db,
        user_id=current_user.id,
        action="webhook_updated",
        entity_type="webhook",
        details={"webhook_id": webhook.id, "updated_fields": sorted(provided)},
    )
    db.commit()
    db.refresh(webhook)
    return _serialize_webhook(db, webhook)


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_webhook(
    webhook_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Delete a webhook subscription and its delivery history (admin only)."""
    webhook = _get_webhook_or_404(db, webhook_id)
    record_audit(
        db,
        user_id=current_user.id,
        action="webhook_deleted",
        entity_type="webhook",
        details={"webhook_id": webhook.id, "name": webhook.name, "url": webhook.url},
    )
    db.delete(webhook)
    db.commit()


@router.post("/{webhook_id}/test")
async def test_webhook(
    webhook_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> dict[str, Any]:
    """Send a signed test event to a webhook (admin only)."""
    webhook = _get_webhook_or_404(db, webhook_id)
    return await send_test_event(db, webhook, triggered_by=current_user.email)


@router.get("/{webhook_id}/deliveries", response_model=list[DeliveryOut])
def list_webhook_deliveries(
    webhook_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
) -> list[WebhookDelivery]:
    """List recent delivery attempts for a webhook, newest first (admin only)."""
    webhook = _get_webhook_or_404(db, webhook_id)
    return (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.webhook_id == webhook.id)
        .order_by(WebhookDelivery.id.desc())
        .limit(limit)
        .all()
    )


@router.post("/post-ingested", response_model=WebhookResponse)
async def post_ingested_webhook(
    request: PostIngestedRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WebhookResponse:
    """Forward a post batch to the configured n8n/Hermes webhook."""
    if request.post_ids:
        posts = db.query(Post).filter(Post.id.in_(request.post_ids)).all()
    else:
        posts = db.query(Post).order_by(Post.id.desc()).limit(100).all()

    payload: dict[str, Any] = {
        "event": "post_ingested",
        "triggered_by": current_user.email,
        "sent_at": datetime.now(timezone.utc),
        "posts": [
            {
                "id": post.id,
                "external_id": post.external_id,
                "platform": post.platform,
                "source_id": post.source_id,
                "title": post.title,
                "content": post.content,
                "author": post.author,
                "source_url": post.source_url or post.post_url,
                "published_at": post.published_at,
                "scraped_at": post.scraped_at,
                "raw_metadata": post.raw_metadata or {},
            }
            for post in posts
        ],
    }
    result = await dispatch_post_ingested(payload, db=db)
    if not result.get("delivered") and result.get("error") == "Webhook URL is not configured":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=result["error"])
    return WebhookResponse(**result)
