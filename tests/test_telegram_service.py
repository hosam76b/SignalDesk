"""Unit tests for the TelegramAdapter service."""

import asyncio
import pytest
from app.services.telegram_service import TelegramAdapter, telegram_adapter


def test_channel_name_extraction():
    """Verify robust parsing of Telegram URLs and @handles."""
    assert TelegramAdapter.extract_channel_name("@durov") == "durov"
    assert TelegramAdapter.extract_channel_name("durov") == "durov"
    assert TelegramAdapter.extract_channel_name("https://t.me/durov") == "durov"
    assert TelegramAdapter.extract_channel_name("https://t.me/s/durov") == "durov"
    assert TelegramAdapter.extract_channel_name("https://t.me/durov/123") == "durov"
    assert TelegramAdapter.extract_channel_name("t.me/my_news_channel") == "my_news_channel"
    assert TelegramAdapter.extract_channel_name("") == ""


def test_telegram_filter_keywords():
    posts = [
        {"title": "News update", "content": "Security warning regarding threat", "platform": "telegram"},
        {"title": "Weather", "content": "Sunny in Cairo today", "platform": "telegram"},
    ]
    filtered = TelegramAdapter._filter_keywords(posts, ["threat", "security"])
    assert len(filtered) == 1
    assert filtered[0]["title"] == "News update"

    # Empty keywords returns all
    assert len(TelegramAdapter._filter_keywords(posts, [])) == 2


def test_telegram_fetch_invalid_channel():
    res = asyncio.run(telegram_adapter.fetch_channel_posts(""))
    assert res["success"] is False
    assert "Invalid Telegram target" in res["error"]

