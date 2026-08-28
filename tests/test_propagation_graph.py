"""Unit and integration tests for Network Propagation Graph and CIB tracking."""

from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Topic, MonitoredSource, Post, User
from app.services.propagation_service import (
    analyze_topic_propagation_graph,
    compute_content_key,
    format_delay,
)


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


def test_format_delay():
    assert format_delay(30) == "+30s"
    assert format_delay(120) == "+2m"
    assert format_delay(3700) == "+1h 1m"
    assert format_delay(90000) == "+1d"


def test_propagation_graph_empty(memory_db):
    topic = Topic(title="Empty Topic", description="No posts")
    memory_db.add(topic)
    memory_db.commit()

    graph = analyze_topic_propagation_graph(memory_db, topic.id)
    assert graph["success"] is True
    assert graph["nodes"] == []
    assert graph["edges"] == []
    assert graph["summary"]["total_nodes"] == 0


def test_propagation_patient_zero_and_cib(memory_db):
    topic = Topic(title="CIB Investigation Topic")
    memory_db.add(topic)
    memory_db.commit()

    source_a = MonitoredSource(topic_id=topic.id, platform="telegram", name="Channel A", url_or_handle="@chan_a")
    source_b = MonitoredSource(topic_id=topic.id, platform="facebook", name="Page B", url_or_handle="https://fb.com/pageb")
    source_c = MonitoredSource(topic_id=topic.id, platform="x", name="Account C", url_or_handle="https://x.com/acctc")
    memory_db.add_all([source_a, source_b, source_c])
    memory_db.commit()

    t0 = datetime(2026, 8, 28, 12, 0, 0)
    # 3 duplicate posts with identical fingerprint within 10 minutes (Coordinated Campaign)
    post_1 = Post(
        topic_id=topic.id,
        source_id=source_a.id,
        external_id="tg_101",
        platform="telegram",
        author="Channel A",
        content="Urgent security alert issued across capital city",
        content_fingerprint="fp_campaign_12345",
        published_at=t0,
        scraped_at=t0,
        severity_level="high",
        is_dangerous=True,
    )
    post_2 = Post(
        topic_id=topic.id,
        source_id=source_b.id,
        external_id="fb_202",
        platform="facebook",
        author="Page B",
        content="Urgent security alert issued across capital city",
        content_fingerprint="fp_campaign_12345",
        published_at=t0 + timedelta(minutes=4),
        scraped_at=t0 + timedelta(minutes=4),
        severity_level="high",
        is_dangerous=True,
    )
    post_3 = Post(
        topic_id=topic.id,
        source_id=source_c.id,
        external_id="x_303",
        platform="x",
        author="Account C",
        content="Urgent security alert issued across capital city",
        content_fingerprint="fp_campaign_12345",
        published_at=t0 + timedelta(minutes=9),
        scraped_at=t0 + timedelta(minutes=9),
        severity_level="high",
        is_dangerous=True,
    )
    memory_db.add_all([post_1, post_2, post_3])
    memory_db.commit()

    graph = analyze_topic_propagation_graph(memory_db, topic.id, cib_window_minutes=30)
    assert graph["success"] is True
    assert graph["summary"]["total_nodes"] == 3
    assert graph["summary"]["total_edges"] == 2
    assert graph["summary"]["cib_clusters_count"] == 1
    assert graph["summary"]["patient_zero_count"] == 1

    # Patient Zero node check
    pz_node = next(n for n in graph["nodes"] if n["id"] == post_1.id)
    assert pz_node["is_patient_zero"] is True
    assert pz_node["is_amplifier"] is False
    assert pz_node["is_cib"] is True

    # Amplifier node check
    amp_node = next(n for n in graph["nodes"] if n["id"] == post_2.id)
    assert amp_node["is_patient_zero"] is False
    assert amp_node["is_amplifier"] is True
    assert amp_node["delay_from_origin"] == "+4m"

