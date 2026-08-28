"""Unit and integration tests for Media Content Extraction (Whisper & OCR)."""

import asyncio
import pytest
from app.services.media_extraction_service import MediaExtractionService, media_extractor


def test_youtube_id_extraction():
    assert MediaExtractionService._extract_youtube_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert MediaExtractionService._extract_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert MediaExtractionService._extract_youtube_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert MediaExtractionService._extract_youtube_id("https://youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert MediaExtractionService._extract_youtube_id("invalid-url") is None


def test_enrich_post_multimodal_no_media():
    post = {
        "platform": "telegram",
        "content": "Standard text post with no audio or image",
        "media_urls": [],
        "post_url": "https://t.me/news/1",
        "raw_metadata": {},
    }
    enriched = asyncio.run(media_extractor.enrich_post_multimodal(post))
    assert enriched["content"] == "Standard text post with no audio or image"
    assert "extracted_media_text" not in enriched.get("raw_metadata", {})


def test_extract_ocr_invalid_url():
    # Should safely return None without crashing
    assert asyncio.run(media_extractor.extract_image_ocr("")) is None
    assert asyncio.run(media_extractor.extract_image_ocr("ftp://not-http.com")) is None

