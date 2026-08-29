"""Async background media processing pipeline (OCR + audio/video transcription).

Runs as fire-and-forget background tasks so scraping and API requests are never
blocked by EasyOCR/Tesseract or faster-whisper processing. Falls back gracefully
(media_status="failed" or fields left null) if those optional dependencies are
unavailable, so posts are always displayed/processed with their raw text.
"""

from __future__ import annotations

import asyncio
import logging

from app.db.session import SessionLocal
from app.models.post import Post
from app.services.media_extraction_service import media_extractor

logger = logging.getLogger(__name__)

MEDIA_STATUS_PENDING = "pending"
MEDIA_STATUS_COMPLETED = "completed"
MEDIA_STATUS_FAILED = "failed"

# Bounds how many posts are OCR'd/transcribed at once. Without this, a scraping
# cycle that saves dozens of posts fires that many concurrent DB sessions and
# exhausts the connection pool, starving normal API requests (dashboard/feed).
_MEDIA_PROCESSING_SEMAPHORE = asyncio.Semaphore(2)


async def process_post_media(post_id: int) -> None:
    """Extract OCR text and an audio/video transcript for one post, in its own DB session."""
    async with _MEDIA_PROCESSING_SEMAPHORE:
        db = SessionLocal()
        try:
            post = db.query(Post).filter(Post.id == post_id).first()
            if post is None:
                return
            try:
                ocr_text: str | None = None
                for media_url in (post.media_urls or [])[:3]:
                    if isinstance(media_url, str) and media_url.startswith(("http://", "https://")):
                        ocr_text = await media_extractor.extract_image_ocr(media_url)
                        if ocr_text:
                            break

                transcript: str | None = None
                candidate_url = post.post_url or post.source_url or ""
                if candidate_url:
                    transcript = await media_extractor.extract_video_transcript(candidate_url, platform=post.platform)

                post.extracted_ocr_text = ocr_text
                post.video_transcript = transcript
                post.media_status = MEDIA_STATUS_COMPLETED
                db.commit()
            except Exception:
                logger.exception("Media processing failed for post %s", post_id)
                db.rollback()
                post.media_status = MEDIA_STATUS_FAILED
                db.commit()
        finally:
            db.close()


def schedule_media_processing(post_id: int) -> None:
    """Fire-and-forget scheduling; never blocks or raises to the caller."""
    try:
        asyncio.create_task(process_post_media(post_id))
    except RuntimeError:
        logger.debug("No running event loop; skipping media processing for post %s", post_id)


def build_combined_text(post: Post) -> str:
    """Merge raw post text with OCR/transcript results for unified sentiment/AI analysis."""
    parts = [post.content or ""]
    if post.extracted_ocr_text:
        parts.append(f"[OCR]: {post.extracted_ocr_text}")
    if post.video_transcript:
        parts.append(f"[Transcript]: {post.video_transcript}")
    return "\n".join(part for part in parts if part).strip()
