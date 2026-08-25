"""Idempotence test for the database seed operation."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import seed
from app.models import Base, MonitoredSource, Topic, User, UserTopic


def test_seed_is_idempotent(monkeypatch):
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(seed, "engine", engine)
    monkeypatch.setattr(seed, "SessionLocal", session_factory)

    seed.seed_database()
    seed.seed_database()

    with session_factory() as db:
        assert db.query(User).filter_by(email=seed.DEFAULT_ADMIN_EMAIL).count() == 1
        assert db.query(Topic).filter_by(title="General Monitoring").count() == 1
        assert db.query(UserTopic).count() == 3
        assert db.query(MonitoredSource).count() == 5
    engine.dispose()
