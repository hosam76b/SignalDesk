"""Media content extraction service for audio/video transcription and OCR image text extraction."""

from __future__ import annotations

import asyncio
import io
import logging
import re
from typing import Any

import httpx
from PIL import Image

from config import settings

logger = logging.getLogger(__name__)

# Attempt pytesseract import
try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None  # type: ignore[assignment]

# Attempt YouTube Transcript API
try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:  # pragma: no cover
    YouTubeTranscriptApi = None  # type: ignore[assignment]

# Attempt faster-whisper or whisper
try:
    from faster_whisper import WhisperModel
except ImportError:  # pragma: no cover
    WhisperModel = None  # type: ignore[assignment]


class MediaExtractionService:
    """Extract textual content from images (OCR) and video/audio media (Whisper/Transcripts)."""

    def __init__(self) -> None:
        self.ocr_enabled = getattr(settings, "ocr_enabled", True)
        self.whisper_model_name = getattr(settings, "whisper_model", "base")
        self._whisper_model = None

    def _get_whisper_model(self):
        """Lazy loader for WhisperModel."""
        if self._whisper_model is None and WhisperModel is not None:
            try:
                self._whisper_model = WhisperModel(self.whisper_model_name, device="cpu", compute_type="int8")
            except Exception as exc:
                logger.warning("Could not initialize local WhisperModel: %s", exc)
        return self._whisper_model

    async def extract_image_ocr(self, image_url: str) -> str | None:
        """Download image and extract text via local OCR."""
        if not self.ocr_enabled or not pytesseract:
            return None

        if not image_url or not image_url.startswith(("http://", "https://")):
            return None

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(image_url)
                if resp.status_code != 200:
                    return None
                image_bytes = resp.content

            # Run OCR in thread
            def _run_ocr(raw_bytes: bytes) -> str:
                img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
                try:
                    # Attempt Arabic + English OCR, fallback to default
                    return pytesseract.image_to_string(img, lang="ara+eng")
                except Exception:
                    return pytesseract.image_to_string(img)

            text = await asyncio.to_thread(_run_ocr, image_bytes)
            cleaned = " ".join(text.strip().split())
            return cleaned if len(cleaned) >= 5 else None

        except Exception as exc:
            logger.debug("OCR extraction skipped/failed for %s: %s", image_url[:80], exc)
            return None

    async def extract_image_ocr_from_path(self, file_path: str) -> str | None:
        """Run local OCR directly on a file already stored on disk (e.g. Quick Ingest uploads)."""
        if not self.ocr_enabled or not pytesseract:
            return None

        def _run_ocr(path: str) -> str:
            img = Image.open(path).convert("RGB")
            try:
                return pytesseract.image_to_string(img, lang="ara+eng")
            except Exception:
                return pytesseract.image_to_string(img)

        try:
            text = await asyncio.to_thread(_run_ocr, file_path)
            cleaned = " ".join(text.strip().split())
            return cleaned if len(cleaned) >= 5 else None
        except Exception as exc:
            logger.debug("OCR extraction skipped/failed for local file %s: %s", file_path, exc)
            return None

    async def extract_video_transcript(self, url_or_id: str, platform: str = "") -> str | None:
        """Extract spoken dialogue or subtitles from YouTube/video URLs."""
        if platform == "youtube" or "youtube.com" in url_or_id or "youtu.be" in url_or_id:
            return await self._extract_youtube_transcript(url_or_id)

        # Local audio transcription with faster-whisper if model available
        whisper = self._get_whisper_model()
        if whisper is not None and url_or_id.lower().endswith((".mp3", ".wav", ".m4a", ".mp4", ".mov", ".webm", ".mkv")):
            try:
                def _transcribe(media_path_or_url: str) -> str:
                    segments, _ = whisper.transcribe(media_path_or_url, beam_size=2)
                    return " ".join([seg.text for seg in segments])

                text = await asyncio.to_thread(_transcribe, url_or_id)
                return text.strip() if text else None
            except Exception as exc:
                logger.debug("Whisper transcription failed: %s", exc)

        return None

    async def _extract_youtube_transcript(self, url_or_id: str) -> str | None:
        """Extract subtitles for YouTube videos using youtube_transcript_api."""
        if not YouTubeTranscriptApi:
            return None

        video_id = self._extract_youtube_id(url_or_id)
        if not video_id:
            return None

        try:
            def _fetch_transcript(vid: str) -> str:
                # Prioritize Arabic and English transcripts
                transcript_list = YouTubeTranscriptApi.list_transcripts(vid)
                try:
                    transcript = transcript_list.find_transcript(["ar", "en", "ar-SA", "en-US"])
                except Exception:
                    transcript = transcript_list.find_generated_transcript(["ar", "en"])
                items = transcript.fetch()
                return " ".join([item.get("text", "") for item in items])

            text = await asyncio.to_thread(_fetch_transcript, video_id)
            cleaned = " ".join(text.strip().split())
            return cleaned[:5000] if cleaned else None
        except Exception as exc:
            logger.debug("YouTube transcript unavailable for %s: %s", video_id, exc)
            return None

    @staticmethod
    def _extract_youtube_id(url_or_id: str) -> str | None:
        """Extract clean video ID from YouTube URL or ID string."""
        if not url_or_id or not isinstance(url_or_id, str):
            return None
        match = re.search(r"(?:v=|\/v\/|\/embed\/|\/shorts\/|youtu\.be\/)([A-Za-z0-9_-]{11})", url_or_id)
        if match:
            return match.group(1)
        if len(url_or_id) == 11 and re.match(r"^[A-Za-z0-9_]{11}$", url_or_id):
            return url_or_id
        return None

    async def enrich_post_multimodal(self, post_dict: dict[str, Any]) -> dict[str, Any]:
        """
        Enrich a scraped post dictionary with extracted OCR and Audio transcripts
        before saving and analyzing with sentiment/AI models.
        """
        extracted_texts: list[str] = []
        platform = post_dict.get("platform", "")
        post_url = post_dict.get("post_url") or post_dict.get("source_url") or ""
        media_urls = post_dict.get("media_urls") or []

        # 1. Video Transcript
        if platform == "youtube" or any(domain in post_url for domain in ("youtube.com", "youtu.be", "tiktok.com")):
            transcript = await self.extract_video_transcript(post_url, platform=platform)
            if transcript:
                extracted_texts.append(f"[Audio Transcript]: {transcript}")

        # 2. Image OCR from attached media (up to first 2 images)
        for media_url in media_urls[:2]:
            if isinstance(media_url, str) and media_url.startswith(("http://", "https://")):
                ocr_text = await self.extract_image_ocr(media_url)
                if ocr_text:
                    extracted_texts.append(f"[Image OCR]: {ocr_text}")
                    break

        if extracted_texts:
            joined_extracted = "\n".join(extracted_texts)
            orig_content = post_dict.get("content", "")
            post_dict["content"] = f"{orig_content}\n\n{joined_extracted}".strip()
            if "raw_metadata" in post_dict and isinstance(post_dict["raw_metadata"], dict):
                post_dict["raw_metadata"]["extracted_media_text"] = joined_extracted

        return post_dict


media_extractor = MediaExtractionService()
