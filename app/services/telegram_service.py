"""Native Telegram channel adapter supporting Telethon MTProto and web preview fallback."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

from config import settings

logger = logging.getLogger(__name__)

try:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
except ImportError:  # pragma: no cover
    TelegramClient = None  # type: ignore[assignment, misc]
    StringSession = None  # type: ignore[assignment, misc]


class TelegramAdapter:
    """Ingest public Telegram channels via Telethon or public web preview."""

    def __init__(self) -> None:
        self.api_id = getattr(settings, "telegram_api_id", "")
        self.api_hash = getattr(settings, "telegram_api_hash", "")
        self.session_string = getattr(settings, "telegram_session_string", "")

    @property
    def is_mtproto_configured(self) -> bool:
        """Return True if Telethon credentials are provided."""
        return bool(self.api_id and self.api_hash and TelegramClient is not None)

    async def fetch_channel_posts(
        self,
        target: str,
        limit: int = 50,
        keywords: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch and normalize messages from a Telegram channel."""
        channel_name = self.extract_channel_name(target)
        if not channel_name:
            return {
                "success": False,
                "posts": [],
                "error": f"Invalid Telegram target or channel username: {target}",
            }

        # Attempt Telethon MTProto if configured
        if self.is_mtproto_configured:
            try:
                posts = await self._fetch_via_telethon(channel_name, limit=limit)
                if posts:
                    filtered = self._filter_keywords(posts, keywords)
                    return {
                        "success": True,
                        "posts": filtered,
                        "error": None,
                        "method": "telethon_mtproto",
                    }
            except Exception as exc:
                logger.warning(
                    "Telethon fetch failed for channel @%s; falling back to web preview: %s",
                    channel_name,
                    exc,
                )

        # Fallback to public web channel preview (t.me/s/channel)
        try:
            posts = await self._fetch_via_web_preview(channel_name, limit=limit)
            filtered = self._filter_keywords(posts, keywords)
            return {
                "success": True,
                "posts": filtered,
                "error": None,
                "method": "telegram_web_preview",
            }
        except Exception as exc:
            logger.exception("Telegram web preview failed for @%s: %s", channel_name, exc)
            return {
                "success": False,
                "posts": [],
                "error": f"Telegram scraping failed: {exc}",
                "method": "telegram_web_preview",
            }

    async def _fetch_via_telethon(self, channel_name: str, limit: int = 50) -> list[dict[str, Any]]:
        """Fetch messages using Telethon async client."""
        if not TelegramClient:
            return []

        session = StringSession(self.session_string) if self.session_string else "media_monitor_session"
        client = TelegramClient(session, int(self.api_id), self.api_hash)
        await client.connect()
        try:
            entity = await client.get_entity(channel_name)
            messages = await client.get_messages(entity, limit=limit)
            posts: list[dict[str, Any]] = []

            for msg in messages:
                if not msg or not (msg.text or msg.message):
                    continue

                content = (msg.text or msg.message or "").strip()
                post_url = f"https://t.me/{channel_name}/{msg.id}"
                external_id = f"tg_{channel_name}_{msg.id}"

                media_urls: list[str] = []
                if msg.media:
                    if isinstance(msg.media, MessageMediaPhoto):
                        media_urls.append(f"https://t.me/{channel_name}/{msg.id}?media=photo")
                    elif isinstance(msg.media, MessageMediaDocument):
                        media_urls.append(f"https://t.me/{channel_name}/{msg.id}?media=document")

                published_at = msg.date.replace(tzinfo=None) if msg.date else datetime.now(timezone.utc).replace(tzinfo=None)

                posts.append({
                    "platform": "telegram",
                    "external_id": external_id,
                    "title": content[:120] if len(content) > 120 else None,
                    "content": content,
                    "raw_text": content,
                    "author": f"@{channel_name}",
                    "source_url": f"https://t.me/{channel_name}",
                    "post_url": post_url,
                    "media_urls": media_urls,
                    "published_at": published_at,
                    "created_at": published_at,
                    "raw_metadata": {
                        "channel": channel_name,
                        "message_id": msg.id,
                        "views": getattr(msg, "views", None),
                        "forwards": getattr(msg, "forwards", None),
                        "edit_date": msg.edit_date.isoformat() if getattr(msg, "edit_date", None) else None,
                    },
                })
            return posts
        finally:
            await client.disconnect()

    async def _fetch_via_web_preview(self, channel_name: str, limit: int = 50) -> list[dict[str, Any]]:
        """Fetch messages from the official Telegram web preview (t.me/s/{channel})."""
        preview_url = f"https://t.me/s/{channel_name}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
        }

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as http_client:
            resp = await http_client.get(preview_url, headers=headers)
            if resp.status_code == 404:
                raise ValueError(f"Telegram channel @{channel_name} does not exist or is private")
            resp.raise_for_status()
            html = resp.text

        soup = BeautifulSoup(html, "html.parser")
        message_elements = soup.select(".tgme_widget_message_wrap")

        posts: list[dict[str, Any]] = []
        for elem in message_elements[-limit:]:
            widget = elem.select_one(".tgme_widget_message")
            if not widget:
                continue

            raw_id = widget.get("data-post", "")  # format: channel/123
            msg_id = raw_id.split("/")[-1] if "/" in raw_id else raw_id
            if not msg_id:
                msg_id = sha256(str(elem).encode()).hexdigest()[:16]

            # Text & caption extraction
            text_elem = elem.select_one(".tgme_widget_message_text")
            content = text_elem.get_text(separator="\n").strip() if text_elem else ""

            # Check for media photos or video thumbnails
            media_urls: list[str] = []
            for photo in elem.select(".tgme_widget_message_photo_wrap"):
                style = photo.get("style", "")
                match = re.search(r"background-image:url\('([^']+)'\)", style)
                if match:
                    media_urls.append(match.group(1))

            for video_thumb in elem.select(".tgme_widget_message_video_thumb"):
                style = video_thumb.get("style", "")
                match = re.search(r"background-image:url\('([^']+)'\)", style)
                if match:
                    media_urls.append(match.group(1))

            if not content and not media_urls:
                continue

            if not content:
                content = f"[Telegram Media Post: @{channel_name}/{msg_id}]"

            # Date extraction
            time_elem = elem.select_one("time")
            published_at = datetime.now(timezone.utc).replace(tzinfo=None)
            if time_elem and time_elem.get("datetime"):
                try:
                    dt_str = time_elem.get("datetime", "")
                    published_at = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).replace(tzinfo=None)
                except Exception:
                    pass

            # Views extraction
            views_elem = elem.select_one(".tgme_widget_message_views")
            views = views_elem.text.strip() if views_elem else None

            post_url = f"https://t.me/{channel_name}/{msg_id}" if "/" in raw_id else f"https://t.me/s/{channel_name}"

            posts.append({
                "platform": "telegram",
                "external_id": f"tg_{channel_name}_{msg_id}",
                "title": content[:120] if len(content) > 120 else None,
                "content": content[:10000],
                "raw_text": content[:10000],
                "author": f"@{channel_name}",
                "source_url": f"https://t.me/{channel_name}",
                "post_url": post_url,
                "media_urls": media_urls,
                "published_at": published_at,
                "created_at": published_at,
                "raw_metadata": {
                    "channel": channel_name,
                    "data_post": raw_id,
                    "views": views,
                    "source_preview_url": preview_url,
                },
            })

        return posts

    @staticmethod
    def extract_channel_name(target: str) -> str:
        """Extract clean channel username from URL or @handle."""
        cleaned = (target or "").strip()
        if not cleaned:
            return ""

        # Remove @ prefix
        cleaned = cleaned.removeprefix("@")

        # Handle full t.me URLs (e.g., https://t.me/channel, https://t.me/s/channel)
        if "t.me/" in cleaned or "telegram.me/" in cleaned:
            parsed = urlsplit(cleaned if "://" in cleaned else f"https://{cleaned}")
            parts = [part for part in parsed.path.split("/") if part and part != "s"]
            if parts:
                return parts[0]

        return cleaned.strip("/").split("/")[0]

    @staticmethod
    def _filter_keywords(posts: list[dict[str, Any]], keywords: list[str] | None) -> list[dict[str, Any]]:
        """Filter posts by keyword list if provided."""
        if not keywords:
            return posts
        terms = [k.lower().strip() for k in keywords if k.strip()]
        if not terms:
            return posts
        matched: list[dict[str, Any]] = []
        for post in posts:
            text = f"{post.get('title', '')} {post.get('content', '')}".lower()
            if any(term in text for term in terms):
                matched.append(post)
        return matched


telegram_adapter = TelegramAdapter()

