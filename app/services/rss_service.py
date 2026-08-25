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


class RSSService:
    """
    Service for parsing RSS and Atom feeds.
    
    Extracts post data from RSS feeds and normalizes it into a standard format.
    """

    def __init__(self):
        """Initialize RSS service."""
        self.feed_parser = feedparser

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

            # Fetch and sanitize the payload before parsing malformed feeds.
            response = httpx.get(feed_url, timeout=timeout, follow_redirects=True)
            response.raise_for_status()
            cleaned_xml = re.sub(
                r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x84\x86-\x9F]',
                '',
                response.content.decode(response.encoding or 'utf-8', errors='replace'),
            )
            feed = self.feed_parser.parse(BytesIO(cleaned_xml.encode('utf-8')))

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
