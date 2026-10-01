"""Regression tests for epoch parsing in normalize_post.

Actors disagree on timestamp unit and type. scraper_one Facebook actors emit
Unix *milliseconds* as an int; treating those as seconds raised
OSError [Errno 22] on Windows, and because the caller skipped malformed items
one-by-one, a run that had actually succeeded reported zero posts.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.services.scraper_service import ScraperService


SECONDS = 1752519380
MILLIS = 1752519380000


def test_milliseconds_and_seconds_agree():
    assert ScraperService._parse_datetime(MILLIS) == ScraperService._parse_datetime(SECONDS)


def test_milliseconds_as_string_is_an_epoch_not_now():
    """A numeric string is an epoch; it must not silently become 'now'."""
    parsed = ScraperService._parse_datetime(str(MILLIS))
    assert parsed == datetime(2025, 7, 14, 18, 56, 20)


def test_seconds_as_string_is_an_epoch():
    assert ScraperService._parse_datetime(str(SECONDS)) == datetime(2025, 7, 14, 18, 56, 20)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2025-07-15T09:23:00.000Z", datetime(2025, 7, 15, 9, 23)),
        ("2025-07-15T09:23:00+00:00", datetime(2025, 7, 15, 9, 23)),
        ("20250715", datetime(2025, 7, 15)),
    ],
)
def test_existing_string_formats_still_work(value, expected):
    assert ScraperService._parse_datetime(value) == expected


def test_unparseable_value_falls_back_to_now_without_raising():
    assert isinstance(ScraperService._parse_datetime("not-a-date"), datetime)


def test_scraper_one_item_normalizes_without_raising():
    """The exact item shape scraper_one emits, end to end."""
    item = {
        "url": "https://www.facebook.com/NSD.Tripoli/posts/pfbid02abc",
        "pageUrl": "https://www.facebook.com/NSD.Tripoli",
        "postText": "بيان رسمي",
        "timestamp": MILLIS,
        "postId": "1425270636463257",
        "author": {"id": "100055", "name": "مديرية أمن طرابلس"},
        "attachments": [{"type": "photo", "url": "https://scontent.xx/p.jpg"}],
    }
    out = ScraperService.normalize_post(item, "facebook", "https://www.facebook.com/NSD.Tripoli")
    assert out["external_id"] == "1425270636463257"
    assert out["author"] == "مديرية أمن طرابلس"
    assert out["published_at"] == datetime(2025, 7, 14, 18, 56, 20)
    assert out["media_urls"] == ["https://scontent.xx/p.jpg"]
    assert out["content"] == "بيان رسمي"


def test_attachments_are_read_as_media():
    """scraper_one nests media under `attachments`, not `photos`."""
    item = {
        "postText": "x",
        "timestamp": SECONDS,
        "url": "https://facebook.com/p/1",
        "attachments": [
            {"type": "photo", "url": "https://a.jpg"},
            {"type": "video", "url": "https://b.mp4"},
        ],
    }
    out = ScraperService.normalize_post(item, "facebook", "https://facebook.com/p/1")
    assert out["media_urls"] == ["https://a.jpg", "https://b.mp4"]
