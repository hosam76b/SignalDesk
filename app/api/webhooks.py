"""Webhook endpoints for external automation workflows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.post import Post
from app.models.user import User
from app.services.webhook_service import dispatch_post_ingested

router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])


class PostIngestedRequest(BaseModel):
    """Optional explicit batch payload for webhook delivery."""

    post_ids: list[int] = Field(default_factory=list, max_length=500)


class WebhookResponse(BaseModel):
    """Webhook delivery result."""

    success: bool
    delivered: bool
    status_code: int | None = None
    error: str | None = None


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
    result = await dispatch_post_ingested(payload)
    if not result.get("delivered") and result.get("error") == "Webhook URL is not configured":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=result["error"])
    return WebhookResponse(**result)
