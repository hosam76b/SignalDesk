"""Batch orchestration for local Ollama post analysis."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.post import Post
from app.services.ai_service import analyze_post_content
from app.services.knowledge_context import get_topic_knowledge_context
from app.services.media_processor import build_combined_text
from app.services.sentiment import analyze_sentiment
from app.services.webhook_service import WEBHOOK_EVENT_ANALYSIS_COMPLETED, dispatch_event_blocking

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

    knowledge_context_by_topic: dict[int, str] = {}

    for post in posts:
        try:
            # Merge raw text with any OCR/audio-transcript results for unified analysis.
            combined_text = build_combined_text(post)
            local_sentiment = analyze_sentiment(combined_text)
            post.sentiment = local_sentiment["label"]
            post.sentiment_score = int(float(local_sentiment["score"]) * 100)

            if post.topic_id not in knowledge_context_by_topic:
                knowledge_context_by_topic[post.topic_id] = get_topic_knowledge_context(db, post.topic_id)
            knowledge_context = knowledge_context_by_topic[post.topic_id]
            prompt_text = (
                f"[Reference context from the topic's knowledge base]:\n{knowledge_context}\n\n[Post content]:\n{combined_text}"
                if knowledge_context else combined_text
            )
            analysis = analyze_post_content(prompt_text)
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

    if result["updated"]:
        try:
            dispatch_event_blocking(db, WEBHOOK_EVENT_ANALYSIS_COMPLETED, {
                "processed": result["processed"],
                "analyzed": result["analyzed"],
                "failed": result["failed"],
                "duration_seconds": result["duration_seconds"],
            })
        except Exception:
            logger.exception("analysis_completed webhook dispatch failed")

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
