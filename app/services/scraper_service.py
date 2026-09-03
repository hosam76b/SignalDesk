"""Hybrid native and Apify multi-platform ingestion service."""

from __future__ import annotations

import asyncio
import logging
import random
import re
from io import BytesIO
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping

import feedparser
import httpx
from urllib.parse import urlsplit

from config import settings
from app.services.apify_service import ApifyService
from app.services.meta_service import MetaGraphService
from app.services.telegram_service import telegram_adapter

logger = logging.getLogger(__name__)

SUPPORTED_PLATFORMS = {
    "rss", "reddit", "youtube", "facebook", "instagram", "x", "twitter", "tiktok", "threads", "telegram",
}
APIFY_PLATFORMS = {"facebook", "instagram", "x", "twitter", "tiktok", "threads"}


class SourceConfigurationError(ValueError):
    """Raised when a source cannot be attempted with the current configuration."""


class ScraperService:
    """Scrape supported platforms with native libraries and Apify fallback."""

    def __init__(self) -> None:
        self.apify = ApifyService()
        self.meta = MetaGraphService()

    async def scrape_source(
        self,
        platform: str,
        target: str,
        *,
        use_apify: bool = False,
        keywords: list[str] | None = None,
        apify_actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Scrape one source and return normalized posts plus errors."""
        platform = platform.lower().strip()
        self._validate_source_configuration(platform, target)
        native_methods = {
            "rss": self.scrape_rss,
            "reddit": self.scrape_reddit,
            "youtube": self.scrape_youtube,
            "facebook": self.scrape_facebook,
            "instagram": self.scrape_instagram,
            "x": self.scrape_x,
            "twitter": self.scrape_x,
            "tiktok": self.scrape_x,
            "threads": self.scrape_x,
        }
        if platform not in native_methods and platform != "telegram":
            return {"success": False, "posts": [], "error": f"Unsupported platform: {platform}"}

        if platform == "telegram":
            return await self.scrape_telegram(target, keywords or [])

        if platform == "facebook" and self.meta.is_configured:
            meta_result = await self.meta.fetch_page_posts(target)
            if meta_result.get("success"):
                return meta_result
            logger.warning("Meta Graph API failed; falling back to Apify: %s", meta_result.get("error"))
        if platform in APIFY_PLATFORMS and self.apify.is_configured:
            return await self.apify.scrape_social_source(
                platform,
                target,
                {"startUrls": [{"url": target}], "resultsLimit": 50},
                actor_id=apify_actor_id,
            )
        if use_apify and self.apify.is_configured:
            return await self.apify.scrape_social_source(platform, target, actor_id=apify_actor_id)

        try:
            posts = await asyncio.to_thread(native_methods[platform], target, keywords or [])
            return {"success": True, "posts": posts, "error": None, "method": "native"}
        except httpx.HTTPError as exc:
            logger.warning("Native %s scraping failed for %s: %s", platform, target, exc)
            if self.apify.is_configured and (
                platform in APIFY_PLATFORMS or use_apify or apify_actor_id
            ):
                logger.info("Falling back to Apify for %s", target)
                fallback = await self.apify.scrape_social_source(platform, target)
                if fallback.get("success"):
                    return fallback
                return {
                    "success": False,
                    "posts": [],
                    "error": f"Native scraping failed: {exc}; Apify fallback failed: {fallback.get('error')}",
                    "method": "apify",
                }
            return {"success": False, "posts": [], "error": str(exc), "method": "native"}
        except Exception as exc:
            logger.exception("Native %s scraping failed for %s", platform, target)
            if self.apify.is_configured and (
                platform in APIFY_PLATFORMS or use_apify or apify_actor_id
            ):
                logger.info("Falling back to Apify for %s", target)
                fallback = await self.apify.scrape_social_source(platform, target)
                if fallback.get("success"):
                    return fallback
                return {
                    "success": False,
                    "posts": [],
                    "error": f"Native scraping failed: {exc}; Apify fallback failed: {fallback.get('error')}",
                    "method": "apify",
                }
            return {"success": False, "posts": [], "error": str(exc), "method": "native"}

    async def scrape_telegram(self, target: str, keywords: list[str] | None = None) -> dict[str, Any]:
        """Fetch posts from a public or private Telegram channel."""
        return await telegram_adapter.fetch_channel_posts(target, limit=50, keywords=keywords)

    @staticmethod
    def _validate_source_configuration(platform: str, target: str) -> None:
        """Reject invalid targets and unavailable credentials before network work."""
        target = (target or "").strip()
        if platform == "telegram" and not target:
            raise SourceConfigurationError("اسم قناة أو رابط Telegram مطلوب")
        if platform == "rss" and not target.lower().startswith(("http://", "https://")):
            raise SourceConfigurationError("رابط RSS غير صالح: يجب أن يبدأ بـ http:// أو https://")
        if platform in APIFY_PLATFORMS and not settings.apify_api_token:
            if not (platform == "facebook" and settings.meta_access_token):
                raise SourceConfigurationError(f"لا يوجد APIFY_API_TOKEN لمنصة {platform}")

    def scrape_rss(self, url: str, _: list[str] | None = None) -> list[dict[str, Any]]:
        """Fetch and parse RSS or Atom entries after removing invalid XML characters."""
        response: httpx.Response | None = None
        for attempt in range(2):
            try:
                response = httpx.get(url, timeout=15, follow_redirects=True)
                response.raise_for_status()
                break
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError) as exc:
                if attempt == 1:
                    raise
                logger.warning("RSS request failed for %s (%s); retrying once", url, exc)
        if response is None:
            raise RuntimeError(f"RSS request failed for {url}")
        raw_xml = response.content.decode(response.encoding or "utf-8", errors="replace")
        cleaned_xml = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x84\x86-\x9F]', '', raw_xml)
        feed = feedparser.parse(BytesIO(cleaned_xml.encode("utf-8")))
        if getattr(feed, "bozo", False) and not feed.entries:
            raise ValueError(f"RSS parsing failed: {feed.bozo_exception}")
        posts: list[dict[str, Any]] = []
        for entry in feed.entries:
            try:
                enriched = dict(entry)
                enriched["media_urls"] = self._extract_rss_media(entry)
                posts.append(self.normalize_post(enriched, "rss", url))
            except Exception as exc:
                logger.warning("Skipping malformed RSS item from %s: %s", url, exc)
        return posts

    @staticmethod
    def _extract_rss_media(entry: Mapping[str, Any]) -> list[str]:
        """Pull image/video links out of RSS enclosures, media:content, and media:thumbnail tags."""
        media: list[str] = []
        for enclosure in entry.get("enclosures") or []:
            href = enclosure.get("href") or enclosure.get("url")
            enclosure_type = str(enclosure.get("type", ""))
            if href and (not enclosure_type or enclosure_type.startswith(("image/", "video/"))) and href not in media:
                media.append(href)
        for link in entry.get("links") or []:
            if link.get("rel") != "enclosure":
                continue
            href = link.get("href")
            link_type = str(link.get("type", ""))
            if href and (not link_type or link_type.startswith(("image/", "video/"))) and href not in media:
                media.append(href)
        for item in (entry.get("media_content") or []) + (entry.get("media_thumbnail") or []):
            href = item.get("url")
            if href and href not in media:
                media.append(href)
        return media

    def scrape_reddit(self, subreddit: str, keywords: list[str] | None = None) -> list[dict[str, Any]]:
        """Fetch the newest public Reddit posts through the RSS endpoint."""
        community_name = self._reddit_name(subreddit)
        terms = [term.lower() for term in (keywords or [])]
        if not community_name:
            raise ValueError("Subreddit name is empty")

        endpoint = f"https://www.reddit.com/r/{community_name}/new.rss"
        user_agents = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        ]
        feed = feedparser.parse(
            endpoint,
            request_headers={"User-Agent": random.choice(user_agents)},
        )
        feed_status = getattr(feed, "status", None)
        if feed_status in {403, 429}:
            return self._fallback_reddit_to_apify(community_name, feed_status)
        if isinstance(feed_status, int) and feed_status >= 400:
            raise RuntimeError(f"Reddit RSS returned HTTP {feed_status}")
        if getattr(feed, "bozo", False) and not feed.entries:
            raise ValueError(f"Reddit RSS parsing failed: {feed.bozo_exception}")

        posts: list[dict[str, Any]] = []
        for entry in feed.entries[:25]:
            title = str(entry.get("title") or "").strip()
            content = str(entry.get("summary") or title).strip()
            if terms and not any(term in content.lower() for term in terms):
                continue

            source_url = str(entry.get("link") or "").strip()
            external_id = str(entry.get("id") or source_url).strip()
            if not external_id:
                external_id = sha256(f"reddit:{source_url}:{title}:{content}".encode()).hexdigest()
            posts.append({
                "platform": "reddit",
                "external_id": external_id,
                "title": title[:1000],
                "content": content[:10000],
                "author": str(entry.get("author") or "[deleted]"),
                "source_url": source_url,
                "post_url": source_url,
                "media_urls": [],
                "published_at": self._parse_reddit_date(entry.get("published_parsed")),
                "raw_metadata": {
                    "subreddit": community_name,
                    "feed_id": entry.get("id"),
                    "published": entry.get("published"),
                },
            })
        return posts

    def _fallback_reddit_to_apify(self, subreddit: str, status_code: int) -> list[dict[str, Any]]:
        """Use Apify for rate-limited Reddit requests when configured."""
        if not settings.apify_api_token:
            logger.warning(
                "Reddit rate-limited (HTTP %s). Add APIFY_API_TOKEN to bypass.",
                status_code,
            )
            return []
        if not self.apify.is_configured:
            logger.warning("APIFY_API_TOKEN is set but APIFY_ACTOR_ID is missing")
            return []

        try:
            result = asyncio.run(
                self.apify.scrape_social_source(
                    "reddit",
                    f"https://www.reddit.com/r/{subreddit}",
                )
            )
            if result.get("success"):
                return result.get("posts", [])
            logger.warning("Apify Reddit fallback failed: %s", result.get("error"))
        except Exception:
            logger.exception("Unexpected error during Apify Reddit fallback")
        return []

    @staticmethod
    def _parse_reddit_date(value: Any) -> datetime:
        """Convert feedparser's ``published_parsed`` time tuple to datetime."""
        if value is not None:
            try:
                return datetime(*value[:6])
            except (TypeError, ValueError):
                pass
        return datetime.now(timezone.utc)

    @staticmethod
    def _reddit_name(value: str) -> str:
        """Extract a subreddit name from r/name or a Reddit URL."""
        cleaned = value.strip().rstrip("/")
        if "/r/" in cleaned:
            cleaned = cleaned.split("/r/", 1)[1].split("/", 1)[0]
        return cleaned.removeprefix("r/").strip("/")

    def scrape_youtube(self, channel_id_or_url: str, _: list[str] | None = None) -> list[dict[str, Any]]:
        """Extract real per-video metadata with yt-dlp (not the channel's tab stubs)."""
        import yt_dlp

        target = channel_id_or_url.strip()
        if not target:
            raise ValueError("YouTube channel URL or ID is empty")
        if not target.startswith(("http://", "https://")):
            target = f"https://www.youtube.com/channel/{target}"

        # A bare channel/handle URL (no tab) makes yt-dlp list its tabs
        # (Videos/Shorts/Live) as flat stub entries instead of real videos.
        known_tabs = ("/videos", "/shorts", "/streams", "/playlists", "/watch", "/community")
        if any(marker in target for marker in ("youtube.com/@", "youtube.com/channel/", "youtube.com/c/")):
            path = urlsplit(target).path.rstrip("/")
            if not any(path.endswith(tab) for tab in known_tabs):
                target = target.rstrip("/") + "/videos"

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": "in_playlist",
            "playlistend": 50,
            "ignoreerrors": True,
        }
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(target, download=False)
        except Exception as exc:
            raise RuntimeError(f"Unable to extract YouTube source {target}: {exc}") from exc
        if not isinstance(info, Mapping):
            raise ValueError(f"yt-dlp returned no metadata for {target}")
        entries = info.get("entries") or [info]
        posts: list[dict[str, Any]] = []
        for entry in entries:
            if not entry:
                continue
            video_id = entry.get("id", "")
            # Flat extraction exposes the real link under "url", not "webpage_url".
            url = entry.get("url") or entry.get("webpage_url")
            if not url or not str(url).startswith(("http://", "https://")):
                url = f"https://www.youtube.com/watch?v={video_id}" if video_id else channel_id_or_url
            # Flat extraction exposes thumbnails as a list, not a single "thumbnail" string.
            thumbnail = entry.get("thumbnail")
            if not thumbnail:
                thumbnails = entry.get("thumbnails") or []
                thumbnail = thumbnails[-1].get("url") if thumbnails else None
            posts.append(self.normalize_post({
                "id": video_id,
                "title": entry.get("title", ""),
                "description": entry.get("description") or entry.get("title", ""),
                "author": entry.get("channel") or entry.get("uploader"),
                "url": url,
                "published_at": entry.get("upload_date") or entry.get("timestamp"),
                "thumbnail": thumbnail,
                "duration": entry.get("duration"),
            }, "youtube", channel_id_or_url))
        return posts

    def scrape_facebook(self, page_id: str, _: list[str] | None = None) -> list[dict[str, Any]]:
        """Fetch public Facebook posts with facebook-scraper."""
        try:
            from facebook_scraper import get_posts
        except ImportError as exc:
            raise RuntimeError(
                "facebook-scraper is not installed; configure APIFY_API_TOKEN for the fallback"
            ) from exc

        options: dict[str, Any] = {"allow_extra_requests": False}
        cookies_file = getattr(settings, "facebook_cookies_file", None)
        if cookies_file:
            options["cookies"] = cookies_file

        posts: list[dict[str, Any]] = []
        try:
            for post in get_posts(page_id, pages=3, options=options):
                try:
                    posts.append(self.normalize_post(post, "facebook", page_id))
                except Exception as exc:
                    logger.warning("Skipping malformed Facebook post from %s: %s", page_id, exc)
        except Exception as exc:
            raise RuntimeError(
                f"Facebook scraping failed for {page_id}; check public access or cookies: {exc}"
            ) from exc
        return posts

    def scrape_instagram(self, profile: str, _: list[str] | None = None) -> list[dict[str, Any]]:
        """Fetch public Instagram posts with instaloader."""
        import instaloader

        loader = instaloader.Instaloader(download_pictures=False, download_videos=False, quiet=True)
        account = instaloader.Profile.from_username(loader.context, profile.removeprefix("@"))
        posts: list[dict[str, Any]] = []
        for post in account.get_posts():
            posts.append(self.normalize_post({
                "id": post.shortcode,
                "caption": post.caption or "",
                "author": account.username,
                "url": f"https://www.instagram.com/p/{post.shortcode}/",
                "published_at": post.date_utc,
                "media_urls": [post.url],
                "likes": post.likes,
                "comments": post.comments,
            }, "instagram", profile))
            if len(posts) >= 50:
                break
        return posts

    def scrape_x(self, url: str, _: list[str] | None = None) -> list[dict[str, Any]]:
        """Use the Apify route for X, since no reliable native library is bundled."""
        raise RuntimeError(f"Native X scraper is unavailable for {url}")

    @staticmethod
    def normalize_post(item: Mapping[str, Any], platform: str, source_url: str) -> dict[str, Any]:
        """Normalize any native-library record to the PostgreSQL Post contract."""
        content = ScraperService._text(item, "raw_text", "message", "postText", "content", "text", "caption", "description", "selftext", "body")
        title = ScraperService._text(item, "title", "headline")
        post_url = ScraperService._text(item, "post_url", "url", "link", "permalink", "postUrl", default=source_url)
        external_id = ScraperService._text(item, "external_id", "id", "shortcode")
        if not external_id:
            external_id = sha256(f"{platform}:{post_url}:{content}".encode()).hexdigest()
        raw_metadata = dict(item)
        raw_metadata["source_url"] = source_url
        media = item.get("media_urls") or item.get("media") or []
        if isinstance(media, str):
            media = [media]
        thumbnail = item.get("thumbnail")
        if thumbnail and thumbnail not in media:
            media = [thumbnail, *media]
        return {
            "platform": platform,
            "external_id": str(external_id),
            "title": title[:1000],
            "content": content[:10000],
            "raw_text": content[:10000],
            "author": ScraperService._text(item, "author", "username", "ownerUsername", default="Unknown"),
            "source_url": ScraperService._text(item, "source", "source_url", default=source_url),
            "source": ScraperService._text(item, "source", "source_url", default=source_url),
            "post_url": post_url[:1000],
            "media_urls": [str(value) for value in media if value][:20],
            "published_at": ScraperService._parse_datetime(item.get("created_at") or item.get("createdAt") or item.get("published_at") or item.get("publishedAt") or item.get("timestamp")),
            "created_at": ScraperService._parse_datetime(item.get("created_at") or item.get("createdAt") or item.get("published_at") or item.get("publishedAt") or item.get("timestamp")),
            "raw_metadata": raw_metadata,
        }

    @staticmethod
    def _text(item: Mapping[str, Any], *keys: str, default: str = "") -> str:
        for key in keys:
            value = item.get(key)
            if value is not None and not isinstance(value, (dict, list)):
                return str(value).strip()
        return default

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value.replace(tzinfo=None)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, timezone.utc).replace(tzinfo=None)
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                if len(value) == 8 and value.isdigit():
                    return datetime.strptime(value, "%Y%m%d")
        return datetime.now(timezone.utc)
