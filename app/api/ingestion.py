"""Global Quick Ingest: single-URL or direct file/screenshot ingestion for any role.

Bypasses the source/keyword approval queue entirely (only sources/keywords used for
recurring scraping require approval) and runs local OCR/Whisper immediately so the
submitting user sees a final result without polling.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, normalize_role
from app.db.session import get_db
from app.models import MonitoredSource, Post, Topic, User, UserTopic
from app.services.audit_service import record_audit
from app.services.media_extraction_service import media_extractor
from app.services.media_processor import process_post_media, schedule_media_processing
from app.services.scraper_orchestrator import ScraperOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ingestion", tags=["Ingestion"])

UPLOAD_ROOT = Path(__file__).resolve().parent.parent.parent / "media_uploads"
UPLOAD_DIR = UPLOAD_ROOT / "quick"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".m4a", ".mp3", ".wav"}

_orchestrator = ScraperOrchestrator()


def _assert_topic_access(db: Session, current_user: User, topic_id: int) -> None:
    """Any assigned role (including observer) may use Quick Ingest for their topics."""
    if normalize_role(current_user.role) == "super_admin":
        return
    assignment = db.query(UserTopic).filter(
        UserTopic.user_id == current_user.id,
        UserTopic.topic_id == topic_id,
    ).first()
    if assignment is None:
        raise HTTPException(status_code=403, detail="You do not have access to this topic")


def _detect_platform(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if "tiktok.com" in host:
        return "tiktok"
    if "facebook.com" in host or "fb.watch" in host:
        return "facebook"
    if "t.me" in host or "telegram" in host:
        return "telegram"
    if "reddit.com" in host:
        return "reddit"
    if "instagram.com" in host:
        return "instagram"
    if host in {"x.com", "twitter.com"} or host.endswith(".x.com") or host.endswith(".twitter.com"):
        return "x"
    return "rss"


def _get_or_create_quick_source(db: Session, topic_id: int, platform: str) -> MonitoredSource:
    source = db.query(MonitoredSource).filter(
        MonitoredSource.topic_id == topic_id,
        MonitoredSource.platform == platform,
        MonitoredSource.name == "Quick Ingest",
    ).first()
    if source is not None:
        return source
    source = MonitoredSource(
        topic_id=topic_id,
        platform=platform,
        name="Quick Ingest",
        url_or_handle="manual://quick-ingest",
        target_type="manual",
        status="active",
        approval_status="approved",
        # Not a real scrapeable target, so keep it out of the recurring background
        # scraping cycle; it only exists as an FK anchor for quick-ingested posts.
        is_active=False,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


class QuickIngestUrlInput(BaseModel):
    topic_id: int
    url: str = Field(min_length=5, max_length=2000)
    backfill: bool = False


class QuickIngestResult(BaseModel):
    saved: int
    platform: str
    post_ids: list[int]


@router.post("/quick-url", response_model=QuickIngestResult, status_code=status.HTTP_201_CREATED)
async def quick_ingest_url(
    payload: QuickIngestUrlInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Paste a post/channel URL for immediate ingestion; skips the approval queue entirely."""
    _assert_topic_access(db, current_user, payload.topic_id)
    if db.query(Topic).filter(Topic.id == payload.topic_id).first() is None:
        raise HTTPException(status_code=404, detail="Topic not found")

    platform = _detect_platform(payload.url)
    try:
        result = await _orchestrator.scraper_service.scrape_source(platform, payload.url, keywords=[])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch this URL: {exc}") from exc
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error") or "Could not fetch this URL")

    posts = result.get("posts", [])
    posts = posts[:50] if payload.backfill else posts[:1]
    if not posts:
        raise HTTPException(status_code=422, detail="No content could be extracted from this URL")

    source = _get_or_create_quick_source(db, payload.topic_id, platform)
    saved_count = _orchestrator._save_posts(db, source, posts, payload.topic_id)

    created_posts = (
        db.query(Post)
        .filter(Post.topic_id == payload.topic_id, Post.source_id == source.id)
        .order_by(Post.id.desc())
        .limit(max(saved_count, 1))
        .all()
    ) if saved_count else []

    record_audit(
        db,
        user_id=current_user.id,
        topic_id=payload.topic_id,
        action="quick_ingest_url",
        entity_type="post",
        details={"url": payload.url, "platform": platform, "backfill": payload.backfill, "saved": saved_count},
    )
    db.commit()

    # Historical backfill can pull dozens of items — process those in the background.
    # A single quick post is awaited so the caller sees the final OCR/transcript result.
    if payload.backfill:
        for post in created_posts:
            schedule_media_processing(post.id)
    else:
        for post in created_posts:
            await process_post_media(post.id)

    return QuickIngestResult(saved=saved_count, platform=platform, post_ids=[post.id for post in created_posts])


class QuickIngestFileResult(BaseModel):
    post_id: int
    media_status: str
    extracted_ocr_text: str | None = None
    video_transcript: str | None = None


@router.post("/quick-file", response_model=QuickIngestFileResult, status_code=status.HTTP_201_CREATED)
async def quick_ingest_file(
    topic_id: int = Form(...),
    caption: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a screenshot or short video/audio clip for immediate local OCR/transcription."""
    _assert_topic_access(db, current_user, topic_id)
    if db.query(Topic).filter(Topic.id == topic_id).first() is None:
        raise HTTPException(status_code=404, detail="Topic not found")

    extension = Path(file.filename or "upload").suffix.lower()
    if extension not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type. Upload an image or a video/audio clip.")

    stored_name = f"{uuid.uuid4().hex}{extension}"
    destination = UPLOAD_DIR / stored_name
    contents = await file.read()
    destination.write_bytes(contents)
    media_url = f"/media/quick/{stored_name}"

    source = _get_or_create_quick_source(db, topic_id, "upload")
    new_post = Post(
        topic_id=topic_id,
        source_id=source.id,
        external_id=f"quick_{stored_name}",
        platform="upload",
        author=current_user.full_name,
        title=None,
        content=caption or "",
        media_urls=[media_url],
        post_url=None,
        source_url=media_url,
        raw_metadata={"quick_ingest": True, "uploaded_by": current_user.id},
        tags=[],
        published_at=datetime.now(timezone.utc),
        scraped_at=datetime.now(timezone.utc),
        is_flagged=False,
        media_status="pending",
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    record_audit(
        db,
        user_id=current_user.id,
        topic_id=topic_id,
        action="quick_ingest_file",
        entity_type="post",
        details={"filename": file.filename, "post_id": new_post.id},
    )
    db.commit()

    try:
        if extension in IMAGE_EXTENSIONS:
            new_post.extracted_ocr_text = await media_extractor.extract_image_ocr_from_path(str(destination))
        else:
            new_post.video_transcript = await media_extractor.extract_video_transcript(str(destination), platform="upload")
        new_post.media_status = "completed"
    except Exception:
        logger.exception("Quick ingest media processing failed for post %s", new_post.id)
        new_post.media_status = "failed"
    db.commit()
    db.refresh(new_post)

    return QuickIngestFileResult(
        post_id=new_post.id,
        media_status=new_post.media_status,
        extracted_ocr_text=new_post.extracted_ocr_text,
        video_transcript=new_post.video_transcript,
    )
