"""Shared isolated fixtures for Phase 1 and Phase 2 tests."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.session import get_db
from app.models import Base, Keyword, MonitoredSource, Post, Topic, User, UserTopic
from main import app


class AuthenticatedClient:
    def __init__(self, client: TestClient, token: str):
        self.client = client
        self.headers = {"Authorization": f"Bearer {token}"}

    def get(self, *args, **kwargs):
        kwargs["headers"] = self._headers(kwargs)
        return self.client.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        kwargs["headers"] = self._headers(kwargs)
        return self.client.post(*args, **kwargs)

    def put(self, *args, **kwargs):
        kwargs["headers"] = self._headers(kwargs)
        return self.client.put(*args, **kwargs)

    def patch(self, *args, **kwargs):
        kwargs["headers"] = self._headers(kwargs)
        return self.client.patch(*args, **kwargs)

    def delete(self, *args, **kwargs):
        kwargs["headers"] = self._headers(kwargs)
        return self.client.delete(*args, **kwargs)

    def _headers(self, kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.update(self.headers)
        return headers


@pytest.fixture(scope="session")
def engine():
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(test_engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture()
def db(engine):
    connection = engine.connect()
    transaction = connection.begin()
    test_session = sessionmaker(bind=connection, expire_on_commit=False)()
    try:
        yield test_session
    finally:
        test_session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture()
def seeded_db(db: Session):
    super_admin = User(email="super@example.com", hashed_password=hash_password("super-pass"), full_name="Super Admin", role="super_admin")
    admin_a = User(email="admin-a@example.com", hashed_password=hash_password("admin-a-pass"), full_name="Topic Admin A", role="topic_admin")
    admin_b = User(email="admin-b@example.com", hashed_password=hash_password("admin-b-pass"), full_name="Topic Admin B", role="topic_admin")
    monitor_a = User(email="monitor-a@example.com", hashed_password=hash_password("monitor-a-pass"), full_name="Topic Monitor A", role="topic_monitor")
    unassigned = User(email="unassigned@example.com", hashed_password=hash_password("unassigned-pass"), full_name="Unassigned User", role="topic_monitor")
    db.add_all([super_admin, admin_a, admin_b, monitor_a, unassigned])
    db.flush()

    topic_a = Topic(title="Topic A", created_by=super_admin)
    topic_b = Topic(title="Topic B", created_by=super_admin)
    db.add_all([topic_a, topic_b])
    db.flush()
    db.add_all([
        UserTopic(user=admin_a, topic=topic_a, role="topic_admin"),
        UserTopic(user=admin_b, topic=topic_b, role="topic_admin"),
        UserTopic(user=monitor_a, topic=topic_a, role="topic_monitor"),
    ])
    source_a = MonitoredSource(topic=topic_a, platform="rss", name="A Feed", url_or_handle="https://example.com/a")
    source_b = MonitoredSource(topic=topic_b, platform="rss", name="B Feed", url_or_handle="https://example.com/b")
    db.add_all([source_a, source_b])
    db.flush()
    db.add_all([
        Keyword(topic=topic_a, word_or_phrase="alpha", category="general"),
        Keyword(topic=topic_b, word_or_phrase="bravo", category="general"),
        Post(topic=topic_a, source=source_a, external_id="a-1", platform="rss", author="author-a", content="Topic A news", published_at=datetime.now(timezone.utc), scraped_at=datetime.now(timezone.utc)),
        Post(topic=topic_b, source=source_b, external_id="b-1", platform="rss", author="author-b", content="Topic B news", published_at=datetime.now(timezone.utc) - timedelta(minutes=1), scraped_at=datetime.now(timezone.utc)),
    ])
    db.commit()
    return {"super_admin": super_admin, "admin_a": admin_a, "admin_b": admin_b, "monitor_a": monitor_a, "unassigned": unassigned, "topic_a": topic_a, "topic_b": topic_b}


@pytest.fixture()
def client(db, seeded_db):
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    test_client = TestClient(app)
    yield test_client
    test_client.close()
    app.dependency_overrides.pop(get_db, None)


def authenticated_client(client, user, password):
    response = client.post("/api/auth/login", json={"email": user.email, "password": password})
    assert response.status_code == 200, f"Login failed for {user.email}: {response.text}"
    return AuthenticatedClient(client, response.json()["access_token"])


@pytest.fixture()
def super_admin_client(client, seeded_db):
    return authenticated_client(client, seeded_db["super_admin"], "super-pass")


@pytest.fixture()
def topic_a_admin_client(client, seeded_db):
    return authenticated_client(client, seeded_db["admin_a"], "admin-a-pass")


@pytest.fixture()
def topic_b_admin_client(client, seeded_db):
    return authenticated_client(client, seeded_db["admin_b"], "admin-b-pass")


@pytest.fixture()
def topic_a_monitor_client(client, seeded_db):
    return authenticated_client(client, seeded_db["monitor_a"], "monitor-a-pass")


@pytest.fixture()
def unassigned_user_client(client, seeded_db):
    return authenticated_client(client, seeded_db["unassigned"], "unassigned-pass")
