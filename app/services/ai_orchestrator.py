"""Batch orchestration for local Ollama post analysis."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.post import Post
from app.services.ai_service import analyze_post_content

logger = logging.getLogger(__name__)


def process_unanalyzed_posts(db: Session, batch_size: int = 50) -> dict[str, Any]:
    """Analyze up to ``batch_size`` pending posts and commit their results."""
    if batch_size < 1:
        raise ValueError("batch_size must be greater than zero")

    started_at = datetime.now(timezone.utc)
    posts = (
        db.query(Post)
        .filter(
            (Post.ai_summary.is_(None))
            | (Post.ai_summary == "")
            | (Post.severity_level.is_(None))
        )
        .order_by(Post.id.asc())
        .limit(batch_size)
        .all()
    )
    result: dict[str, Any] = {
        "success": True,
        "processed": len(posts),
        "analyzed": 0,
        "updated": 0,
        "failed": 0,
        "errors": [],
        "duration_seconds": 0.0,
    }

    for post in posts:
        try:
            analysis = analyze_post_content(post.content)
            if not analysis["success"]:
                result["failed"] += 1
                result["errors"].append({"post_id": post.id, "error": analysis["error"]})
                continue

            post.violence_category = analysis["violence_category"]
            post.severity_level = analysis["severity_level"]
            post.ai_summary = analysis["ai_summary"]
            post.raw_ai_response = analysis["raw_response"]
            post.is_flagged = analysis["is_flagged"]
            result["analyzed"] += 1
        except Exception as exc:
            logger.exception("Failed to analyze post %s: %s", post.id, exc)
            result["failed"] += 1
            result["errors"].append({"post_id": post.id, "error": str(exc)})

    if result["analyzed"]:
        try:
            db.commit()
            result["updated"] = result["analyzed"]
        except Exception as exc:
            db.rollback()
            result["success"] = False
            result["errors"].append({"error": f"Database commit failed: {exc}"})
            result["updated"] = 0

    result["duration_seconds"] = (datetime.now(timezone.utc) - started_at).total_seconds()
    return result


class AIOrchestrator:
    """Compatibility wrapper around the module-level batch processor."""

    def process_unanalyzed_posts(self, db: Session, batch_size: int = 50) -> dict[str, Any]:
        """Process a bounded batch of pending posts."""
        return process_unanalyzed_posts(db, batch_size)

    def get_flagged_posts(
        self,
        db: Session,
        severity_level: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return flagged posts and all high/critical posts with pagination."""
        query = db.query(Post).filter(
            (Post.is_flagged.is_(True)) | (Post.severity_level.in_(["high", "critical"]))
        )
        if severity_level:
            if severity_level not in {"low", "medium", "high", "critical"}:
                raise ValueError("Invalid severity level")
            query = query.filter(Post.severity_level == severity_level)

        posts = query.order_by(Post.id.desc()).offset(offset).limit(limit).all()
        return {
            "success": True,
            "total_count": query.count(),
            "returned": len(posts),
            "limit": limit,
            "offset": offset,
            "posts": [
                {
                    "id": post.id,
                    "source": post.source.name if post.source else "Unknown",
                    "source_id": post.source_id,
                    "platform": post.platform,
                    "author": post.author,
                    "content": post.content[:500],
                    "post_url": post.post_url,
                    "published_at": post.published_at.isoformat() if post.published_at else None,
                    "scraped_at": post.scraped_at.isoformat() if post.scraped_at else None,
                    "severity_level": post.severity_level,
                    "violence_category": post.violence_category,
                    "ai_summary": post.ai_summary,
                    "is_flagged": post.is_flagged,
                }
                for post in posts
            ],
        }


ai_orchestrator = AIOrchestrator()
