"""Dashboard statistics and recent post activity endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.post import Post
from app.models.user import User

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


class DashboardStatsResponse(BaseModel):
    """Aggregated counts used by the dashboard."""

    total_posts: int
    posts_by_platform: dict[str, int]
    posts_by_severity: dict[str, int]
    flagged_posts: int


class RecentActivityPost(BaseModel):
    """Standard post fields returned by the recent activity feed."""

    id: int
    external_id: str
    platform: str
    source_id: int
    source_url: str | None = None
    title: str | None = None
    content: str
    author: str
    published_at: datetime
    scraped_at: datetime
    post_url: str | None = None
    media_urls: list[Any] = Field(default_factory=list)
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    violence_category: str | None = None
    severity_level: str | None = None
    ai_summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_flagged: bool
    is_important: bool
    is_dangerous: bool
    sentiment: str | None = None
    sentiment_score: int | None = None

    @classmethod
    def from_post(cls, post: Post) -> "RecentActivityPost":
        """Convert a database post into the dashboard activity contract."""
        return cls(
            id=post.id,
            external_id=post.external_id,
            platform=post.platform,
            source_id=post.source_id,
            source_url=post.source_url,
            title=post.title,
            content=post.content,
            author=post.author,
            published_at=post.published_at,
            scraped_at=post.scraped_at,
            post_url=post.post_url,
            media_urls=post.media_urls if isinstance(post.media_urls, list) else [],
            raw_metadata=post.raw_metadata if isinstance(post.raw_metadata, dict) else {},
            violence_category=post.violence_category,
            severity_level=post.severity_level,
            ai_summary=post.ai_summary,
            tags=post.tags if isinstance(post.tags, list) else [],
            is_flagged=post.is_flagged,
            is_important=post.is_important,
            is_dangerous=post.is_dangerous,
            sentiment=post.sentiment,
            sentiment_score=post.sentiment_score,
        )


@router.get("/stats", response_model=DashboardStatsResponse)
def get_dashboard_stats(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DashboardStatsResponse:
    """Return total, platform, severity, and flagged-post counts."""
    total_posts = db.query(func.count(Post.id)).scalar() or 0
    flagged_posts = (
        db.query(func.count(Post.id))
        .filter(Post.is_flagged.is_(True))
        .scalar()
        or 0
    )

    platform_rows = (
        db.query(Post.platform, func.count(Post.id))
        .group_by(Post.platform)
        .all()
    )
    severity_counts = {level: 0 for level in ("low", "medium", "high", "critical")}
    severity_rows = (
        db.query(Post.severity_level, func.count(Post.id))
        .group_by(Post.severity_level)
        .all()
    )
    for severity, count in severity_rows:
        if severity in severity_counts:
            severity_counts[severity] = count

    return DashboardStatsResponse(
        total_posts=total_posts,
        posts_by_platform={platform or "unknown": count for platform, count in platform_rows},
        posts_by_severity=severity_counts,
        flagged_posts=flagged_posts,
    )


@router.get("/recent-activity", response_model=list[RecentActivityPost])
def get_recent_activity(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[RecentActivityPost]:
    """Return the 15 most recently ingested posts."""
    posts = (
        db.query(Post)
        .order_by(Post.scraped_at.desc(), Post.id.desc())
        .limit(15)
        .all()
    )
    return [RecentActivityPost.from_post(post) for post in posts]
