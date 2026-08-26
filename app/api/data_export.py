"""Read and write APIs for external automation integrations."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.post import Post
from app.models.user import User

router = APIRouter(prefix="/api", tags=["Data Integration"])


class PostExport(BaseModel):
    """Stable post contract for n8n, Hermes, and custom consumers."""

    id: int
    topic_id: int
    external_id: str
    platform: str
    source_id: int
    source_url: str | None
    title: str | None
    content: str
    author: str
    published_at: datetime
    scraped_at: datetime
    post_url: str | None
    media_urls: list[Any] = Field(default_factory=list)
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    violence_category: str | None
    severity_level: str | None
    ai_summary: str | None
    tags: list[str] = Field(default_factory=list)
    is_flagged: bool
    is_important: bool
    is_dangerous: bool

    @classmethod
    def from_post(cls, post: Post) -> "PostExport":
        metadata = post.raw_metadata if isinstance(post.raw_metadata, dict) else {}
        return cls(
            id=post.id,
            topic_id=post.topic_id,
            external_id=post.external_id,
            platform=post.platform,
            source_id=post.source_id,
            source_url=post.source_url or metadata.get("source_url") or post.post_url,
            title=post.title,
            content=post.content,
            author=post.author,
            published_at=post.published_at,
            scraped_at=post.scraped_at,
            post_url=post.post_url,
            media_urls=post.media_urls if isinstance(post.media_urls, list) else [],
            raw_metadata=metadata,
            violence_category=post.violence_category,
            severity_level=post.severity_level,
            ai_summary=post.ai_summary,
            tags=post.tags if isinstance(post.tags, list) else [],
            is_flagged=post.is_flagged,
            is_important=post.is_important,
            is_dangerous=post.is_dangerous,
        )


class PostAnalysisUpdate(BaseModel):
    """Analysis result submitted by an external automation workflow."""

    severity_level: Literal["low", "medium", "high", "critical"]
    ai_summary: str = Field(min_length=1, max_length=10000)
    tags: list[str] = Field(default_factory=list, max_length=100)
    is_flagged: bool


@router.get("/data/posts/latest", response_model=list[PostExport])
def latest_posts(
    since: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[PostExport]:
    """Return recently scraped posts for polling consumers."""
    query = db.query(Post)
    if since is not None:
        query = query.filter(Post.scraped_at > since)
    posts = query.order_by(Post.scraped_at.desc(), Post.id.desc()).limit(limit).all()
    return [PostExport.from_post(post) for post in posts]


@router.get("/data/posts/stream", response_model=list[PostExport], include_in_schema=False)
def stream_posts(
    since: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[PostExport]:
    """Compatibility alias for consumers using the stream route."""
    return latest_posts(since=since, limit=limit, db=db, _=_) 


@router.patch("/posts/{post_id}/analysis", response_model=PostExport)
def update_post_analysis(
    post_id: int,
    update: PostAnalysisUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PostExport:
    """Persist externally generated analysis for one ingested post."""
    post = db.query(Post).filter(Post.id == post_id).first()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    post.severity_level = update.severity_level
    post.ai_summary = update.ai_summary
    post.tags = sorted(set(tag.strip() for tag in update.tags if tag.strip()))
    post.is_flagged = update.is_flagged or update.severity_level in {"high", "critical"}
    db.commit()
    db.refresh(post)
    return PostExport.from_post(post)
