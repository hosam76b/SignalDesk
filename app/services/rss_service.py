"""
RSS/Atom Feed Scraping Service.
Parses RSS and Atom feeds to extract post data.
"""

import logging
import re
from io import BytesIO
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import feedparser
import httpx
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

#: Feed validators keyed by feed URL. Lets a poll send a conditional GET so an
#: unchanged feed costs one 304 response instead of a full body transfer and a
#: full re-parse. Without this every 5-minute cycle re-downloads and re-parses
#: every feed in the system, which is the dominant cost of an idle scrape cycle.
_CONDITIONAL_CACHE: Dict[str, Dict[str, str]] = {}


class RSSService:
    """
    Service for parsing RSS and Atom feeds.
    
    Extracts post data from RSS feeds and normalizes it into a standard format.
    """

    def __init__(self):
        """Initialize RSS service."""
        self.feed_parser = feedparser

    def _conditional_headers(self, feed_url: str) -> Dict[str, str]:
        """Build If-None-Match / If-Modified-Since headers for ``feed_url``."""
        cached = _CONDITIONAL_CACHE.get(feed_url)
        if not cached:
            return {}
        headers: Dict[str, str] = {}
        if cached.get("etag"):
            headers["If-None-Match"] = cached["etag"]
        if cached.get("last_modified"):
            headers["If-Modified-Since"] = cached["last_modified"]
        return headers

    @staticmethod
    def _remember_validators(feed_url: str, response: httpx.Response) -> None:
        etag = response.headers.get("etag")
        last_modified = response.headers.get("last-modified")
        if etag or last_modified:
            _CONDITIONAL_CACHE[feed_url] = {
                "etag": etag or "",
                "last_modified": last_modified or "",
            }

    def parse_feed(self, feed_url: str, timeout: int = 10) -> Dict[str, Any]:
        """
        Parse RSS/Atom feed from URL.

        Args:
            feed_url (str): URL to the RSS/Atom feed.
            timeout (int): Request timeout in seconds.

        Returns:
            Dict containing:
                - 'success': bool - Whether parsing succeeded
                - 'error': str - Error message if failed
                - 'posts': List[Dict] - Normalized post data
                - 'feed_title': str - Feed title
                - 'feed_description': str - Feed description

        Example:
            result = rss_service.parse_feed('https://example.com/feed.xml')
            if result['success']:
                for post in result['posts']:
                    print(post['title'], post['link'])
        """
        try:
            logger.info(f"🔄 Parsing RSS feed: {feed_url}")

            # Conditional GET: an unchanged feed answers 304 and costs no body
            # transfer and no parse.
            headers = self._conditional_headers(feed_url)
            response = httpx.get(
                feed_url,
                timeout=timeout,
                follow_redirects=True,
                headers=headers or None,
            )
            if response.status_code == 304:
                logger.debug(f"⏭️  RSS feed unchanged (304): {feed_url}")
                return {
                    "success": True,
                    "error": None,
                    "posts": [],
                    "feed_title": None,
                    "feed_description": None,
                    "not_modified": True,
                }
            response.raise_for_status()
            self._remember_validators(feed_url, response)

            cleaned_xml = re.sub(
                r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x84\x86-\x9F]',
                '',
                response.content.decode(response.encoding or 'utf-8', errors='replace'),
            )
            feed = self._parse_feed_bytes(cleaned_xml)

            # Check for parsing errors
            if feed.bozo and feed.bozo_exception:
                logger.warning(f"⚠️  Feed parsing warning for {feed_url}: {feed.bozo_exception}")

            # Extract posts
            posts = self._extract_posts(feed)

            # Extract feed metadata
            feed_info = feed.get("feed", {})
            feed_title = feed_info.get("title", "Unknown Feed")
            feed_description = feed_info.get("description", "")

            logger.info(f"✅ Parsed {len(posts)} posts from RSS feed")

            return {
                "success": True,
                "error": None,
                "posts": posts,
                "feed_title": feed_title,
                "feed_description": feed_description,
            }

        except Exception as e:
            logger.error(f"❌ Error parsing RSS feed {feed_url}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "posts": [],
                "feed_title": None,
                "feed_description": None,
            }

    def _parse_feed_bytes(self, cleaned_xml: str) -> Any:
        """Parse sanitized feed XML.

        ``feedparser`` is pure-Python and CPU-bound, so it is offloaded to a
        worker thread. Called from the async scraping path via
        ``parse_feed_async``, keeping a large feed from stalling the event loop.
        """
        return self.feed_parser.parse(BytesIO(cleaned_xml.encode('utf-8')))

    async def parse_feed_async(self, feed_url: str, timeout: int = 10) -> Dict[str, Any]:
        """Non-blocking :meth:`parse_feed`; the HTTP fetch and the parse are both
        moved off the event loop."""
        import asyncio

        return await asyncio.to_thread(self.parse_feed, feed_url, timeout)

    def _extract_posts(self, feed: Any) -> List[Dict[str, Any]]:
        """
        Extract individual posts from parsed feed.

        Args:
            feed: Parsed feed object from feedparser.

        Returns:
            List of normalized post dictionaries.
        """
        posts = []

        for entry in feed.get("entries", []):
            try:
                post = {
                    "external_id": self._get_post_id(entry),
                    "platform": "rss",
                    "author": entry.get("author", "Unknown"),
                    "title": entry.get("title", "No Title"),
                    "content": self._extract_content(entry),
                    "post_url": entry.get("link", ""),
                    "published_at": self._parse_date(entry),
                    "media_urls": self._extract_media(entry),
                }

                posts.append(post)

            except Exception as e:
                logger.warning(f"⚠️  Error extracting RSS post: {str(e)}")
                continue

        return posts

    def _get_post_id(self, entry: Any) -> str:
        """
        Extract unique post ID from feed entry.

        Args:
            entry: Feed entry object.

        Returns:
            Unique post identifier.
        """
        # Try multiple ID sources
        if "id" in entry:
            return entry["id"]
        if "link" in entry:
            return entry["link"]
        if "title" in entry:
            return f"rss_{hash(entry['title']) % 10**8}"
        return f"rss_unknown_{datetime.now(timezone.utc).timestamp()}"

    def _extract_content(self, entry: Any) -> str:
        """
        Extract post content/description from entry.

        Args:
            entry: Feed entry object.

        Returns:
            Post content text.
        """
        # Prefer summary over description
        if "summary" in entry:
            content = entry["summary"]
        elif "description" in entry:
            content = entry["description"]
        elif "content" in entry and entry["content"]:
            content = entry["content"][0].get("value", "")
        else:
            content = ""

        # Remove HTML tags (basic cleanup)
        content = self._strip_html(content)
        return content[:5000]  # Limit to 5000 chars

    def _strip_html(self, text: str) -> str:
        """
        Remove HTML tags from text.

        Args:
            text (str): Text with potential HTML.

        Returns:
            Text without HTML tags.
        """
        import re
        return re.sub(r"<[^>]+>", "", text)

    def _extract_media(self, entry: Any) -> List[str]:
        """
        Extract media URLs from feed entry.

        Args:
            entry: Feed entry object.

        Returns:
            List of media URLs.
        """
        media_urls = []

        # Check for enclosures (podcasts, videos)
        for enclosure in entry.get("enclosures", []):
            if "href" in enclosure:
                media_urls.append(enclosure["href"])

        # Check for media_content
        for media in entry.get("media_content", []):
            if "url" in media:
                media_urls.append(media["url"])

        # Check for image tags
        if "media_thumbnail" in entry:
            for thumb in entry["media_thumbnail"]:
                if "url" in thumb:
                    media_urls.append(thumb["url"])

        return media_urls

    def _parse_date(self, entry: Any) -> datetime:
        """
        Parse publication date from feed entry.

        Args:
            entry: Feed entry object.

        Returns:
            Parsed datetime object or current time if parsing fails.
        """
        try:
            # Try published_parsed first (pre-parsed by feedparser)
            if "published_parsed" in entry and entry["published_parsed"]:
                return datetime(*entry["published_parsed"][:6])

            # Try updated_parsed
            if "updated_parsed" in entry and entry["updated_parsed"]:
                return datetime(*entry["updated_parsed"][:6])

            # Try parsing string dates
            if "published" in entry:
                # Basic ISO format parsing
                date_str = entry["published"].split("T")[0]
                return datetime.strptime(date_str, "%Y-%m-%d")

            return datetime.now(timezone.utc)

        except Exception as e:
            logger.warning(f"⚠️  Could not parse date: {str(e)}")
            return datetime.now(timezone.utc)
