"""Dashboard statistics and recent post activity endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.cache import TTLCache
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.post import Post
from app.models.user import User

from config import settings

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

#: Process-local cache for the aggregate panels. Keyed by a constant because the
#: values are the same for every operator -- do not widen the key to per-user
#: data without also scoping the cache per user.
_stats_cache = TTLCache(maxsize=16)


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


def _compute_dashboard_stats(db: Session) -> DashboardStatsResponse:
    """Run the aggregate queries. Split out so the cache can wrap it."""
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


@router.get("/stats", response_model=DashboardStatsResponse)
def get_dashboard_stats(
    response: Response,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DashboardStatsResponse:
    """Return total, platform, severity, and flagged-post counts.

    The aggregates are identical for every operator and only move as posts are
    ingested, so they are cached for ``DASHBOARD_CACHE_TTL_SECONDS``. Panel
    reloads therefore stop issuing four full aggregate scans each.
    """
    ttl = float(getattr(settings, "dashboard_cache_ttl_seconds", 15) or 0)
    payload = _stats_cache.get_or_set(
        "dashboard:stats", ttl, lambda: _compute_dashboard_stats(db)
    )
    response.headers["X-Cache"] = "HIT" if ttl > 0 else "BYPASS"
    response.headers["Cache-Control"] = f"private, max-age={int(ttl)}" if ttl > 0 else "no-store"
    return payload


#: Rows pulled from the database per dedupe page while assembling a page of
#: activity. Keeps memory bounded regardless of how aggressively the caller
#: pages and how many near-duplicates exist.
_DEDUPE_PAGE = 200

#: Hard ceiling on rows scanned for a single request. Without it, a pathological
#: duplicate ratio would let one request walk the whole table.
_MAX_SCAN = 2000


@router.get("/recent-activity", response_model=list[RecentActivityPost])
def get_recent_activity(
    limit: int = Query(default=15, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[RecentActivityPost]:
    """Return a deduplicated page of recently ingested posts.

    ``limit``/``offset`` apply to the *deduplicated* sequence, so paging is
    stable and predictable rather than a raw SQL window. Rows are read in
    bounded pages and the scan stops as soon as enough unique posts are found,
    capped at ``_MAX_SCAN`` rows.
    """
    target = offset + limit
    unique_posts: list[Post] = []
    seen_external_ids: set[str] = set()
    seen_urls: set[str] = set()
    seen_fingerprints: set[str] = set()

    scanned = 0
    while len(unique_posts) < target and scanned < _MAX_SCAN:
        page = (
            db.query(Post)
            .order_by(Post.scraped_at.desc(), Post.id.desc())
            .offset(scanned)
            .limit(_DEDUPE_PAGE)
            .all()
        )
        if not page:
            break
        scanned += len(page)
        for post in page:
            external_id = (post.external_id or "").strip()
            post_url = (post.post_url or "").strip()
            fingerprint = (post.content_fingerprint or "").strip()
            if (
                (external_id and external_id in seen_external_ids)
                or (post_url and post_url in seen_urls)
                or (fingerprint and fingerprint in seen_fingerprints)
            ):
                continue
            unique_posts.append(post)
            if external_id:
                seen_external_ids.add(external_id)
            if post_url:
                seen_urls.add(post_url)
            if fingerprint:
                seen_fingerprints.add(fingerprint)
            if len(unique_posts) >= target:
                break
        if len(page) < _DEDUPE_PAGE:
            break

    return [RecentActivityPost.from_post(post) for post in unique_posts[offset:target]]

