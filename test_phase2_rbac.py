"""Standalone HTTP verification for topic-scoped RBAC."""

import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.session import get_db
from app.models import Base, User
from main import app


def main():
    engine = create_engine(
        "sqlite://",
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
    try:
        with session_factory() as db:
            db.add(User(
                email="phase2-super@example.com",
                hashed_password=hash_password("super-password"),
                full_name="Phase 2 SuperAdmin",
                role="super_admin",
            ))
            db.commit()

        client = TestClient(app)
        try:
            def login(email: str, password: str) -> dict:
                response = client.post("/api/auth/login", json={"email": email, "password": password})
                assert response.status_code == 200, response.text
                return {"Authorization": f"Bearer {response.json()['access_token']}"}

            super_headers = login("phase2-super@example.com", "super-password")
            topic_a = client.post("/api/v1/topics", headers=super_headers, json={"title": "Topic A"})
            topic_b = client.post("/api/v1/topics", headers=super_headers, json={"title": "Topic B"})
            assert topic_a.status_code == 201, topic_a.text
            assert topic_b.status_code == 201, topic_b.text
            topic_a_id = topic_a.json()["id"]
            topic_b_id = topic_b.json()["id"]

            user_admin = client.post(
                "/api/users",
                headers=super_headers,
                json={
                    "email": "phase2-admin-a@example.com",
                    "password": "admin-password",
                    "full_name": "User Admin A",
                    "role": "topic_admin",
                },
            )
            assert user_admin.status_code == 201, user_admin.text
            client.post(
                f"/api/v1/topics/{topic_a_id}/assign-user",
                headers=super_headers,
                json={"user_id": user_admin.json()["id"], "role": "topic_admin"},
            ).raise_for_status()

            admin_headers = login("phase2-admin-a@example.com", "admin-password")
            source = client.post(
                f"/api/v1/topics/{topic_a_id}/sources",
                headers=admin_headers,
                json={"platform": "rss", "name": "Topic A Feed", "url_or_handle": "https://example.com/a"},
            )
            assert source.status_code == 201, source.text

            forbidden_source = client.post(
                f"/api/v1/topics/{topic_b_id}/sources",
                headers=admin_headers,
                json={"platform": "rss", "name": "Topic B Feed", "url_or_handle": "https://example.com/b"},
            )
            forbidden_news = client.get(f"/api/v1/topics/{topic_b_id}/news", headers=admin_headers)
            assert forbidden_source.status_code == 403
            assert forbidden_news.status_code == 403

            all_topics = client.get("/api/v1/topics", headers=super_headers)
            assert all_topics.status_code == 200
            assert {topic["title"] for topic in all_topics.json()} >= {"Topic A", "Topic B"}

            print(json.dumps({
                "step_2_success": True,
                "rbac_isolation_verified": True,
                "forbidden_access_caught": True,
            }))
        finally:
            client.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


if __name__ == "__main__":
    main()