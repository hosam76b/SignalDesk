"""Safety-net tests: explicit self-harm/violence must never pass as clean."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.post import Post
from app.models.source import MonitoredSource
from app.models.topic import Topic
from app.models.user import User
from app.services import ai_orchestrator as orchestrator_module
from app.services.media_processor import build_combined_text
from app.services.risk_signals import apply_risk_signals, clean_text, screen_text

# The Reddit RSS payload exactly as scrapers store it: raw HTML plus entities.
REDDIT_HTML_POST = (
    '<!-- SC_OFF --><div class="md"><p>هموت وانتحر عشان اتبضنت من الدنيا وتعبت اوي بجد '
    'اتبضنت وعندي مرض مش لاقيله علاج اي افكار للانتحار يشباب بس متكنش مولمه</p></div>'
    '<!-- SC_ON --> &#32; submitted by &#32; <a href="https://www.reddit.com/user/franklin__56">'
    '/u/franklin__56</a>'
)


def test_clean_text_strips_html_comments_tags_and_entities():
    cleaned = clean_text(REDDIT_HTML_POST)
    assert "<div" not in cleaned
    assert "SC_OFF" not in cleaned
    assert "&#32;" not in cleaned
    assert "هموت وانتحر" in cleaned


def test_reddit_suicide_post_is_screened_as_critical_self_harm():
    signal = screen_text(REDDIT_HTML_POST)
    assert signal is not None
    assert signal["violence_category"] == "self_harm"
    assert signal["severity_level"] == "critical"


@pytest.mark.parametrize("text,category", [
    ("I want to kill myself tonight", "self_harm"),
    ("عايز انتحر مش قادر اكمل", "self_harm"),
    ("هقتلك لو شفتك تاني", "physical_violence"),
    ("معايا مسدس وذخيرة كتير", "weapon_related"),
])
def test_risk_rules_cover_arabic_and_english(text, category):
    signal = screen_text(text)
    assert signal is not None and signal["violence_category"] == category


def test_clean_content_is_not_screened():
    assert screen_text("مباراة كرة قدم ممتعة انتهت بالتعادل") is None


def test_risk_signals_escalate_but_never_downgrade():
    under_rated = {"success": True, "severity_level": "low", "violence_category": None,
                   "is_flagged": False, "ai_summary": "منشور عادي"}
    escalated = apply_risk_signals(under_rated, "عايز انتحر")
    assert escalated["severity_level"] == "critical"
    assert escalated["violence_category"] == "self_harm"
    assert escalated["is_flagged"] is True

    already_critical = {"success": True, "severity_level": "critical", "violence_category": "extremism",
                        "is_flagged": True, "ai_summary": "تهديد"}
    kept = apply_risk_signals(already_critical, "معايا مسدس")
    assert kept["severity_level"] == "critical"
    assert kept["violence_category"] == "extremism"


def _seed_post(db: Session, content: str) -> Post:
    user = User(email=f"risk-{time.time_ns()}@example.com", hashed_password=hash_password("pw"),
                full_name="Risk User", role="super_admin")
    db.add(user)
    db.flush()
    topic = Topic(title=f"Topic {time.time_ns()}", created_by=user)
    db.add(topic)
    db.flush()
    source = MonitoredSource(platform="reddit", name="Reddit", url_or_handle="https://reddit.com/r/x")
    db.add(source)
    db.flush()
    now = datetime.now(timezone.utc)
    post = Post(topic_id=topic.id, source_id=source.id, external_id=f"ext-{time.time_ns()}",
                platform="reddit", author="franklin__56", content=content,
                published_at=now, scraped_at=now)
    db.add(post)
    db.flush()
    return post


def test_combined_text_feeds_clean_content_to_the_model(db: Session):
    post = _seed_post(db, REDDIT_HTML_POST)
    combined = build_combined_text(post)
    assert "<div" not in combined
    assert "هموت وانتحر" in combined


def test_batch_flags_self_harm_even_when_model_under_rates(db: Session, monkeypatch):
    post = _seed_post(db, REDDIT_HTML_POST)

    async def under_rating_model(_text: str, _images=None):
        return {
            "success": True,
            "provider": "ollama",
            "violence_category": None,
            "severity_level": "low",
            "ai_summary": "منشور شخصي عادي",
            "is_flagged": False,
            "detected_entities": [],
            "sentiment_score": -10,
            "raw_response": {},
            "error": None,
        }

    monkeypatch.setattr(orchestrator_module.ai_service, "analyze_post_content_async", under_rating_model)
    monkeypatch.setattr(orchestrator_module, "dispatch_event_blocking", lambda *_a, **_k: None)

    result = orchestrator_module.process_unanalyzed_posts(db, batch_size=10)

    db.refresh(post)
    assert result["risk_flagged"] == 1
    assert post.severity_level == "critical"
    assert post.violence_category == "self_harm"
    assert post.is_flagged is True
    assert post.is_dangerous is True


def test_batch_flags_self_harm_when_all_providers_fail(db: Session, monkeypatch):
    post = _seed_post(db, REDDIT_HTML_POST)

    async def failing_model(_text: str, _images=None):
        return orchestrator_module.fallback_result("all providers unavailable")

    monkeypatch.setattr(orchestrator_module.ai_service, "analyze_post_content_async", failing_model)
    monkeypatch.setattr(orchestrator_module, "dispatch_event_blocking", lambda *_a, **_k: None)

    result = orchestrator_module.process_unanalyzed_posts(db, batch_size=10)

    db.refresh(post)
    assert result["failed"] == 1
    assert result["risk_flagged"] == 1
    assert post.is_dangerous is True
    assert post.violence_category == "self_harm"
    # ai_summary stays empty so the post is retried once a provider recovers.
    assert not post.ai_summary
