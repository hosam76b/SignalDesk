"""Seed the database with roles, an initial admin, and sample sources."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from app.core.security import hash_password
from app.db.session import Base, SessionLocal, engine
from app.models import Keyword, MonitoredSource, Post, Topic, User, UserTopic

DEFAULT_ADMIN_EMAIL = "admin@example.com"
DEFAULT_ADMIN_PASSWORD = "admin123"
TEST_USERS = (
    ("topic-admin@example.com", "topicadmin123", "Topic Administrator", "topic_admin"),
    ("monitor@example.com", "monitor123", "Read Only Monitor", "topic_monitor"),
)


def seed_database() -> None:
    """Create baseline tables and insert idempotent development seed data."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        admin = db.query(User).filter(User.email == DEFAULT_ADMIN_EMAIL).first()
        if admin is None:
            admin = User(
                email=DEFAULT_ADMIN_EMAIL,
                hashed_password=hash_password(DEFAULT_ADMIN_PASSWORD),
                full_name="Administrator",
                role="super_admin",
                is_active=True,
            )
            db.add(admin)
            db.flush()

        topic = db.query(Topic).filter(Topic.title == "General Monitoring").first()
        if topic is None:
            topic = Topic(title="General Monitoring", description="Default monitoring topic", created_by=admin)
            db.add(topic)
            db.flush()

        assignment = db.query(UserTopic).filter(
            UserTopic.user_id == admin.id,
            UserTopic.topic_id == topic.id,
        ).first()
        if assignment is None:
            db.add(UserTopic(user=admin, topic=topic, role="topic_admin"))

        topic_a = db.query(Topic).filter(Topic.title == "Child Safety Monitoring").first()
        if topic_a is None:
            topic_a = Topic(title="Child Safety Monitoring", description="Safeguarding and child violence signals", created_by=admin)
            db.add(topic_a)
            db.flush()
        topic_b = db.query(Topic).filter(Topic.title == "Public Health Signals").first()
        if topic_b is None:
            topic_b = Topic(title="Public Health Signals", description="Public health and community risk monitoring", created_by=admin)
            db.add(topic_b)
            db.flush()

        test_users = {}
        for email, password, full_name, role in TEST_USERS:
            user = db.query(User).filter(User.email == email).first()
            if user is None:
                user = User(email=email, hashed_password=hash_password(password), full_name=full_name, role=role, is_active=True)
                db.add(user)
                db.flush()
            test_users[role] = user

        for role, user, assigned_topic in (
            ("topic_admin", test_users["topic_admin"], topic_a),
            ("topic_monitor", test_users["topic_monitor"], topic_a),
        ):
            if db.query(UserTopic).filter(UserTopic.user_id == user.id, UserTopic.topic_id == assigned_topic.id).first() is None:
                db.add(UserTopic(user=user, topic=assigned_topic, role=role))

        for assigned_topic, word in ((topic_a, "child safety"), (topic_b, "public health")):
            if db.query(Keyword).filter(Keyword.topic_id == assigned_topic.id, Keyword.word_or_phrase == word).first() is None:
                db.add(Keyword(topic=assigned_topic, word_or_phrase=word, category="safety"))

        sample_sources = (
            ("rss", "Sample RSS Feed", "https://example.com/feed.xml", None),
            ("facebook", "Sample Apify Facebook", "https://www.facebook.com/example", "apify/facebook-posts-scraper"),
        )
        for platform, name, target, actor_id in sample_sources:
            exists = db.query(MonitoredSource).filter(
                MonitoredSource.url_or_handle == target,
            ).first()
            if exists is None:
                db.add(MonitoredSource(
                    platform=platform,
                    name=name,
                    url_or_handle=target,
                    target_type="url",
                    apify_actor_id=actor_id,
                    status="active",
                ))
        topic_sources = (
            (topic_a, "rss", "Child Safety RSS", "https://example.com/child-safety.xml", None),
            (topic_a, "facebook", "Child Safety Apify", "https://www.facebook.com/example-child-safety", "apify/facebook-posts-scraper"),
            (topic_b, "youtube", "Public Health YouTube", "https://www.youtube.com/@example-health", "apify/youtube-scraper"),
        )
        for assigned_topic, platform, name, target, actor_id in topic_sources:
            source = db.query(MonitoredSource).filter(MonitoredSource.url_or_handle == target).first()
            if source is None:
                source = MonitoredSource(platform=platform, name=name, url_or_handle=target, target_type="url", apify_actor_id=actor_id, status="active")
                db.add(source)
                db.flush()
            post = db.query(Post).filter(Post.external_id == f"seed-{assigned_topic.id}-{source.id}").first()
            if post is None:
                timestamp = datetime.now(timezone.utc) - timedelta(hours=2 if assigned_topic is topic_a else 4)
                db.add(Post(topic=assigned_topic, source=source, external_id=f"seed-{assigned_topic.id}-{source.id}", platform=platform, author="seed-fixture", title=f"{assigned_topic.title} sample signal", content=f"Sample {assigned_topic.title} content for manual testing.", published_at=timestamp, scraped_at=timestamp))
        db.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the media monitoring database")
    parser.parse_args()
    seed_database()
    print(f"Seed complete. Admin login: {DEFAULT_ADMIN_EMAIL} / {DEFAULT_ADMIN_PASSWORD}")
