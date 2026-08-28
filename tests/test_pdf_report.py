"""Unit and integration tests for PDF Report Generator."""

from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Topic, MonitoredSource, Post, User
from app.services.pdf_report_service import generate_topic_executive_pdf, sanitize_text


@pytest.fixture
def memory_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def test_sanitize_text():
    assert sanitize_text("Dangerous <script> & alert") == "Dangerous &lt;script&gt; &amp; alert"
    assert sanitize_text(None) == ""


def test_generate_pdf_report_success(memory_db):
    user = User(email="analyst@agency.gov", hashed_password="pw", full_name="Chief Intelligence Analyst", role="super_admin")
    topic = Topic(title="Counter-Terrorism & Extremism", description="Monitoring threats across Telegram and social pages")
    memory_db.add_all([user, topic])
    memory_db.commit()

    source = MonitoredSource(topic_id=topic.id, platform="telegram", name="Intel Channel", url_or_handle="@intel_feed")
    memory_db.add(source)
    memory_db.commit()

    post = Post(
        topic_id=topic.id,
        source_id=source.id,
        external_id="tg_999",
        platform="telegram",
        author="@intel_feed",
        content="Hostile propaganda and weapons smuggling report in sector 4",
        published_at=datetime(2026, 8, 28, 14, 0, 0),
        scraped_at=datetime(2026, 8, 28, 14, 5, 0),
        severity_level="critical",
        violence_category="weapon_related",
        ai_summary="Detected active illicit arms trafficking content",
        is_flagged=True,
        is_dangerous=True,
        sentiment="negative",
    )
    memory_db.add(post)
    memory_db.commit()

    pdf_bytes = generate_topic_executive_pdf(memory_db, topic.id, requester=user)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 500
    assert pdf_bytes.startswith(b"%PDF-")  # Valid PDF signature


def test_generate_pdf_invalid_topic(memory_db):
    with pytest.raises(ValueError, match="Topic 9999 not found"):
        generate_topic_executive_pdf(memory_db, 9999)

