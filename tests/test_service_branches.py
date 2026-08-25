"""Additional branch coverage for deterministic service behavior."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.ai_service import AIAnalysisService
from app.services.playwright_service import PlaywrightService
from app.services.reddit_service import RedditService
from app.services.rss_service import RSSService
from app.services.scraper_service import ScraperService
from app.services.webhook_service import build_n8n_post_payload, dispatch_post_ingested
from app.models import Post, Topic


def test_ai_service_fallback_and_normalization():
    service = AIAnalysisService()
    service.client = None
    result = service.analyze_post_content("")
    assert result["success"] is False
    assert AIAnalysisService._normalize_result({"violence_category": "unknown", "severity_level": "critical"})["violence_category"] == "other"


def test_rss_success_path(monkeypatch):
    class Response:
        content = b"<rss/>"
        encoding = "utf-8"

        def raise_for_status(self):
            return None

    class Feed(dict):
        bozo = False
        bozo_exception = None

    feed = Feed(entries=[{"id": "1", "title": "Alpha", "summary": "Body", "link": "https://example.com/1"}], feed={"title": "Feed"})
    monkeypatch.setattr("httpx.get", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr("feedparser.parse", lambda *_args, **_kwargs: feed)
    result = RSSService().parse_feed("https://example.com/feed")
    assert result["success"] is True
    assert result["feed_title"] == "Feed"
    assert len(result["posts"]) == 1


def test_scraper_rss_and_reddit_paths(monkeypatch):
    service = ScraperService()
    monkeypatch.setattr(service, "scrape_rss", lambda *_args: [{"title": "Alpha", "content": "Body"}])
    result = asyncio.run(service.scrape_source("rss", "https://example.com/feed"))
    assert result["success"] is True

    feed = SimpleNamespace(status=200, bozo=False, entries=[{"title": "Alpha", "summary": "alpha body", "link": "https://reddit/1", "id": "r1"}])
    monkeypatch.setattr("feedparser.parse", lambda *_args, **_kwargs: feed)
    posts = service.scrape_reddit("r/test", ["alpha"])
    assert posts[0]["external_id"] == "r1"
    assert service._reddit_name("https://reddit.com/r/test/") == "test"


def test_reddit_unconfigured_and_hot_posts():
    service = RedditService()
    service.reddit = None
    result = service.search_subreddit("test", ["alpha"])
    assert result["success"] is False
    assert service.get_hot_posts("test")["posts"] == []


def test_youtube_failure_and_date_parse():
    from app.services.youtube_service import YouTubeService
    service = YouTubeService.__new__(YouTubeService)
    service.youtube = None
    assert service.search_videos("alpha")["success"] is False
    assert service.get_transcript("missing")["success"] is False
    assert service._parse_date("invalid").tzinfo == timezone.utc


def test_playwright_extraction_paths():
    class Page:
        async def evaluate(self, *_args):
            return [{"external_id": "p1", "author": "author", "content": "content"}]

    service = PlaywrightService()
    posts = asyncio.run(service._extract_posts_by_platform(Page(), "facebook", "https://example.com"))
    assert posts[0]["platform"] == "facebook"
    assert asyncio.run(service._extract_posts_by_platform(Page(), "unknown", "https://example.com")) == []


def test_webhook_disabled_and_payload():
    result = asyncio.run(dispatch_post_ingested({"event": "test"}))
    assert result["delivered"] is False
    topic = Topic(id=1, title="Topic", description="Description")
    post = Post(id=1, topic_id=1, source_id=1, external_id="p", platform="rss", author="a", content="c", published_at=datetime.now(timezone.utc), scraped_at=datetime.now(timezone.utc))
    payload = build_n8n_post_payload(post, topic)
    assert payload["topic_id"] == 1
    assert "Topic" in payload["ai_prompt"]
