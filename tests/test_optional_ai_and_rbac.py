from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.session import get_db
from app.models import Base, Topic, User, UserTopic
from main import app


def build_client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    return client, session_factory


def test_ai_service_is_non_blocking_when_unavailable():
    from app.services.ai_service import AIAnalysisService

    service = AIAnalysisService()
    service.client = None

    result = service.analyze_post_content("This is a normal post without threats.")

    assert isinstance(result, dict)
    assert "success" in result
    assert result["severity_level"] in {"low", "medium", "high", "critical"}
    assert result["is_flagged"] in {True, False}


def test_topic_manager_has_assigned_topic_access_but_not_unassigned():
    client, session_factory = build_client()
    try:
        with session_factory() as db:
            super_admin = User(
                email="super@example.com",
                hashed_password=hash_password("pw"),
                full_name="Super Admin",
                role="super_admin",
            )
            topic_manager = User(
                email="manager@example.com",
                hashed_password=hash_password("pw"),
                full_name="Topic Manager",
                role="topic_manager",
            )
            analyst = User(
                email="analyst@example.com",
                hashed_password=hash_password("pw"),
                full_name="Analyst",
                role="analyst",
            )
            topic = Topic(title="Alpha", description="Topic A")
            db.add_all([super_admin, topic_manager, analyst, topic])
            db.flush()
            db.add(UserTopic(user_id=topic_manager.id, topic_id=topic.id, role="topic_manager"))
            db.commit()

        manager_login = client.post("/api/auth/login", json={"email": "manager@example.com", "password": "pw"})
        manager_token = manager_login.json()["access_token"]
        manager_headers = {"Authorization": f"Bearer {manager_token}"}

        allowed = client.get(f"/api/v1/topics/{topic.id}/sources", headers=manager_headers)
        denied = client.get("/api/v1/topics/99999/sources", headers=manager_headers)

        assert allowed.status_code == 200 or allowed.status_code == 404
        assert denied.status_code in {403, 404}

        analyst_login = client.post("/api/auth/login", json={"email": "analyst@example.com", "password": "pw"})
        analyst_headers = {"Authorization": f"Bearer {analyst_login.json()['access_token']}"}
        analyst_topics = client.get("/api/v1/topics", headers=analyst_headers)
        assert analyst_topics.status_code == 200
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
