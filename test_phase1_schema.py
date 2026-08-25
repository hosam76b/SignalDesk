"""Phase 1 database schema, integrity, cascade, and migration tests."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import init_db as init_module
from app.models import Keyword, MonitoredSource, Post


def test_topic_id_foreign_keys_and_cascades(db, seeded_db):
    topic_a = seeded_db["topic_a"]
    source = db.query(MonitoredSource).filter_by(topic_id=topic_a.id).one()
    keyword = db.query(Keyword).filter_by(topic_id=topic_a.id).one()
    post = db.query(Post).filter_by(topic_id=topic_a.id).one()

    assert source.topic_id == topic_a.id, "Source must retain its owning topic_id"
    assert keyword.topic_id == topic_a.id, "Keyword must retain its owning topic_id"
    assert post.topic_id == topic_a.id, "Post must retain its owning topic_id"

    db.delete(topic_a)
    db.commit()
    assert db.get(MonitoredSource, source.id) is None, "Deleting a topic must cascade to its sources"
    assert db.get(Keyword, keyword.id) is None, "Deleting a topic must cascade to its keywords"
    assert db.get(Post, post.id) is None, "Deleting a topic must cascade to its posts"


def test_source_and_keyword_require_valid_topic(db, seeded_db):
    with pytest.raises(IntegrityError, match="NOT NULL"):
        db.add(MonitoredSource(platform="rss", name="Orphan", url_or_handle="https://orphan", topic_id=None))
        db.commit()
    db.rollback()

    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        db.add(MonitoredSource(platform="rss", name="Invalid", url_or_handle="https://invalid", topic_id=999999))
        db.commit()
    db.rollback()

    with pytest.raises(IntegrityError, match="NOT NULL"):
        db.add(Keyword(word_or_phrase="orphan", category="general", topic_id=None))
        db.commit()
    db.rollback()


def test_legacy_rows_are_backfilled_to_general_topic(tmp_path, monkeypatch):
    from sqlalchemy import create_engine

    legacy_engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}", future=True)
    with legacy_engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, role VARCHAR(50))"))
        connection.execute(text("CREATE TABLE monitored_sources (id INTEGER PRIMARY KEY, platform VARCHAR(50), name VARCHAR(255), url_or_handle VARCHAR(500))"))
        connection.execute(text("CREATE TABLE keywords (id INTEGER PRIMARY KEY, word_or_phrase VARCHAR(500))"))
        connection.execute(text("CREATE TABLE posts (id INTEGER PRIMARY KEY, source_id INTEGER, platform VARCHAR(50), author VARCHAR(255), content TEXT)"))
        connection.execute(text("INSERT INTO monitored_sources VALUES (1, 'rss', 'Legacy', 'https://legacy')"))
        connection.execute(text("INSERT INTO keywords VALUES (1, 'legacy')"))
        connection.execute(text("INSERT INTO posts VALUES (1, 1, 'rss', 'author', 'legacy post')"))
        connection.execute(text("INSERT INTO users VALUES (1, 'admin')"))

    monkeypatch.setattr(init_module, "engine", legacy_engine)
    init_module.migrate_topic_schema()
    with legacy_engine.connect() as connection:
        topic_id = connection.execute(text("SELECT id FROM topics WHERE title = 'General Monitoring'")).scalar_one()
        assert connection.execute(text("SELECT topic_id FROM monitored_sources WHERE id = 1")).scalar_one() == topic_id, "Legacy sources must be backfilled"
        assert connection.execute(text("SELECT topic_id FROM keywords WHERE id = 1")).scalar_one() == topic_id, "Legacy keywords must be backfilled"
        assert connection.execute(text("SELECT topic_id FROM posts WHERE id = 1")).scalar_one() == topic_id, "Legacy posts must be backfilled"
        assert connection.execute(text("SELECT role FROM users WHERE id = 1")).scalar_one() == "super_admin", "Legacy admin role must be migrated"
    legacy_engine.dispose()
