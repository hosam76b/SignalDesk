"""Concurrent batch orchestration for multi-provider post analysis."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.keyword import Keyword
from app.models.post import Post
from app.models.topic import PromptTemplate, Topic
from app.services.ai_service import ai_service, fallback_result, run_sync
from app.services.knowledge_context import get_topic_knowledge_context
from app.services.media_processor import build_combined_text, collect_image_refs, load_inline_images
from app.services.risk_signals import apply_risk_signals
from app.services.sentiment import analyze_sentiment
from app.services.webhook_service import WEBHOOK_EVENT_ANALYSIS_COMPLETED, dispatch_event_blocking
from config import settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _AnalysisTask:
    """Everything one post needs for analysis, detached from the DB session."""

    post_id: int
    prompt_text: str
    combined_text: str = ""
    image_refs: list[str] = field(default_factory=list)


def _latest_active_prompt(db: Session, topic_id: int) -> PromptTemplate | None:
    """Return the newest active prompt template for a topic, if one exists."""
    return (
        db.query(PromptTemplate)
        .filter(PromptTemplate.topic_id == topic_id, PromptTemplate.is_active == 1)
        .order_by(PromptTemplate.updated_at.desc(), PromptTemplate.id.desc())
        .first()
    )


def _topic_keywords(db: Session, topic_id: int) -> str:
    keywords = (
        db.query(Keyword)
        .filter(Keyword.topic_id == topic_id, Keyword.is_active.is_(True))
        .order_by(Keyword.id.asc())
        .limit(50)
        .all()
    )
    return ", ".join(keyword.word_or_phrase for keyword in keywords) or "No active keywords configured."


def _post_context(post: Post, combined_text: str) -> str:
    return "\n".join([
        f"- ID: {post.id}",
        f"  Platform: {post.platform}",
        f"  Author: {post.author}",
        f"  Published: {post.published_at.isoformat() if post.published_at else 'unknown'}",
        f"  Title: {post.title or ''}",
        f"  Content: {combined_text[:6000]}",
    ])


def _render_analysis_prompt(db: Session, post: Post, combined_text: str, knowledge_context: str) -> str:
    topic = db.query(Topic).filter(Topic.id == post.topic_id).first()
    prompt_template = _latest_active_prompt(db, post.topic_id)
    post_context = _post_context(post, combined_text)
    context = {
        "topic_name": topic.title if topic else "Topic",
        "posts_content": post_context,
        "post_content": combined_text,
        "keywords": _topic_keywords(db, post.topic_id),
        "time_range": "current post",
        "knowledge_context": knowledge_context or "No knowledge base documents for this topic.",
    }

    if prompt_template is None:
        return (
            f"[Topic]: {context['topic_name']}\n"
            f"[Keywords]: {context['keywords']}\n"
            f"[Reference context from the topic's knowledge base]:\n{knowledge_context}\n\n"
            f"[Post content]:\n{post_context}"
        )

    rendered = prompt_template.template
    for key, value in context.items():
        rendered = rendered.replace(f"{{{key}}}", str(value))

    if "{posts_content}" not in prompt_template.template and "{post_content}" not in prompt_template.template:
        rendered = (
            f"{rendered}\n\n"
            "[Actual monitored content for this analysis]\n"
            f"Topic: {context['topic_name']}\n"
            f"Time range: {context['time_range']}\n"
            f"Keywords: {context['keywords']}\n\n"
            f"Post:\n{post_context}\n\n"
            f"Knowledge context:\n{context['knowledge_context']}"
        )
    return rendered


def _sentiment_fallback_summary(analysis: dict[str, Any]) -> str:
    if analysis.get("risk_signals"):
        return str(analysis.get("ai_summary") or "رصد آلي لمؤشرات خطورة بانتظار التحليل الكامل")
    return "تم تحليل المشاعر محلياً؛ لم يتوفر مزود ذكاء اصطناعي لإنتاج ملخص متقدم."


async def _analyze_tasks(tasks: list[_AnalysisTask]) -> dict[int, dict[str, Any]]:
    """Run provider calls concurrently under a bounded semaphore."""
    limit = max(1, int(getattr(settings, "ai_max_concurrency", 5) or 5))
    semaphore = asyncio.Semaphore(limit)
    max_images = max(0, int(getattr(settings, "ai_max_images_per_post", 2) or 0))
    use_vision = max_images > 0 and ai_service.supports_vision

    async def _run(task: _AnalysisTask) -> tuple[int, dict[str, Any]]:
        async with semaphore:
            images = await load_inline_images(task.image_refs, max_images) if (use_vision and task.image_refs) else []
            return task.post_id, await ai_service.analyze_post_content_async(task.prompt_text, images)

    outcomes = await asyncio.gather(*(_run(task) for task in tasks), return_exceptions=True)
    analyses: dict[int, dict[str, Any]] = {}
    for task, outcome in zip(tasks, outcomes):
        if isinstance(outcome, BaseException):
            logger.error("Analysis task failed for post %s: %s", task.post_id, outcome)
            analyses[task.post_id] = fallback_result(str(outcome))
        else:
            analyses[outcome[0]] = outcome[1]
    return analyses


def process_unanalyzed_posts(db: Session, batch_size: int = 50) -> dict[str, Any]:
    """Analyze up to ``batch_size`` pending posts concurrently and commit their results."""
    if batch_size < 1:
        raise ValueError("batch_size must be greater than zero")

    posts = (
        db.query(Post)
        .filter(
            (Post.ai_summary.is_(None))
            | (Post.ai_summary == "")
            | (Post.severity_level.is_(None))
        )
        .order_by(Post.scraped_at.desc(), Post.id.desc())
        .limit(batch_size)
        .all()
    )
    return _process_posts(db, posts)


def process_posts_by_ids(db: Session, post_ids: list[int]) -> dict[str, Any]:
    """Analyze the specified posts, preserving ingestion order as much as possible."""
    clean_ids = list(dict.fromkeys(int(post_id) for post_id in post_ids if post_id))
    if not clean_ids:
        return _process_posts(db, [])
    posts = db.query(Post).filter(Post.id.in_(clean_ids)).all()
    posts_by_id = {post.id: post for post in posts}
    return _process_posts(db, [posts_by_id[post_id] for post_id in clean_ids if post_id in posts_by_id])


def auto_analyze_posts(db: Session, post_ids: list[int]) -> dict[str, Any]:
    """Best-effort automatic analysis for newly ingested posts."""
    try:
        return process_posts_by_ids(db, post_ids)
    except Exception as exc:
        logger.exception("Automatic post analysis failed: %s", exc)
        return {"success": False, "processed": 0, "analyzed": 0, "updated": 0, "failed": len(post_ids), "errors": [str(exc)]}


def _process_posts(db: Session, posts: list[Post]) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    result: dict[str, Any] = {
        "success": True,
        "processed": len(posts),
        "analyzed": 0,
        "updated": 0,
        "failed": 0,
        "risk_flagged": 0,
        "errors": [],
        "duration_seconds": 0.0,
    }

    max_images = max(0, int(getattr(settings, "ai_max_images_per_post", 2) or 0))
    posts_by_id = {post.id: post for post in posts}
    tasks: list[_AnalysisTask] = []
    skipped_empty = 0

    # Phase 1: build prompts on the session thread so no DB access happens concurrently.
    for post in posts:
        try:
            # Merge raw text with any OCR/audio-transcript results for unified analysis.
            combined_text = build_combined_text(post)
            local_sentiment = analyze_sentiment(combined_text)
            post.sentiment = local_sentiment["label"]
            post.sentiment_score = int(float(local_sentiment["score"]) * 100)

            if not combined_text:
                post.violence_category = None
                post.severity_level = "low"
                post.ai_summary = "لا يوجد محتوى نصي قابل للتحليل"
                post.raw_ai_response = {"skipped": "empty_content"}
                post.is_flagged = False
                skipped_empty += 1
                continue

            knowledge_context = get_topic_knowledge_context(db, post.topic_id, query=combined_text)
            prompt_text = _render_analysis_prompt(db, post, combined_text, knowledge_context)
            tasks.append(_AnalysisTask(
                post_id=post.id,
                prompt_text=prompt_text,
                combined_text=combined_text,
                image_refs=collect_image_refs(post, max_images) if max_images else [],
            ))
        except Exception as exc:
            logger.exception("Failed to prepare post %s for analysis: %s", post.id, exc)
            result["failed"] += 1
            result["errors"].append({"post_id": post.id, "error": str(exc)})

    # Phase 2: fan out the provider calls concurrently, then persist on this thread.
    analyses = run_sync(_analyze_tasks(tasks)) if tasks else {}
    text_by_post = {task.post_id: task.combined_text for task in tasks}
    has_pending_writes = bool(posts)
    sentiment_fallbacks = 0

    for post_id, analysis in analyses.items():
        post = posts_by_id.get(post_id)
        if post is None:
            continue

        # Rule-based screening runs on every outcome so explicit self-harm/violence
        # is never left unflagged when the model fails or under-rates it.
        analysis = apply_risk_signals(analysis, text_by_post.get(post_id, ""))

        if not analysis["success"]:
            result["failed"] += 1
            result["errors"].append({"post_id": post_id, "error": analysis["error"]})
            post.violence_category = analysis.get("violence_category")
            post.severity_level = analysis.get("severity_level") or "low"
            post.ai_summary = _sentiment_fallback_summary(analysis)
            post.raw_ai_response = analysis.get("raw_response") or {"error": analysis.get("error")}
            post.is_flagged = bool(analysis.get("is_flagged"))
            if analysis.get("risk_signals"):
                post.is_dangerous = True
                result["risk_flagged"] += 1
            sentiment_fallbacks += 1
            continue

        post.violence_category = analysis["violence_category"]
        post.severity_level = analysis["severity_level"]
        post.ai_summary = analysis["ai_summary"]
        post.raw_ai_response = analysis["raw_response"]
        post.is_flagged = analysis["is_flagged"]
        if analysis.get("risk_signals"):
            post.is_dangerous = True
            result["risk_flagged"] += 1
        if analysis.get("detected_entities"):
            post.entities = analysis["detected_entities"]
        result["analyzed"] += 1

    if result["analyzed"] or skipped_empty or has_pending_writes:
        try:
            db.commit()
            result["updated"] = result["analyzed"] + skipped_empty + sentiment_fallbacks
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
