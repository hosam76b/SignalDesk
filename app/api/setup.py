"""Unauthenticated, one-time installation endpoints for a new SignalDesk instance."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.db import session as database_session
from app.db.init_db import migrate_topic_schema
from app.db.session import Base, get_db
from app.models import Topic, User, UserTopic
from app.services.audit_service import record_audit
from config import settings

router = APIRouter(prefix="/api/setup", tags=["Initial setup"])
_initialization_lock = threading.Lock()
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


class DatabaseConfig(BaseModel):
    type: str = Field(pattern="^(sqlite|postgresql)$")
    path: str = "media_monitor.db"
    host: str = "localhost"
    port: int = Field(default=5432, ge=1, le=65535)
    name: str = "media_monitor"
    username: str = ""
    password: str = ""

    def url(self) -> str:
        if self.type == "sqlite":
            database_path = Path(self.path).expanduser()
            if not database_path.is_absolute():
                database_path = Path(__file__).resolve().parents[2] / database_path
            return f"sqlite:///{database_path.resolve().as_posix()}"
        credentials = quote_plus(self.username)
        secret = quote_plus(self.password)
        return f"postgresql://{credentials}:{secret}@{self.host}:{self.port}/{self.name}"


class InitializeRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email_or_username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)
    database: DatabaseConfig
    app_name: str = Field(default="SignalDesk", min_length=2, max_length=100)
    ai_provider: str = Field(default="ollama", pattern="^(ollama|gemini|google_ai_studio|openrouter|custom_openai)$")
    ai_api_key: str = Field(default="", max_length=1000)
    monitoring_interval_minutes: int = Field(default=5, ge=1, le=1440)

    @model_validator(mode="after")
    def passwords_match(self) -> "InitializeRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        if not any(character.isalpha() for character in self.password) or not any(character.isdigit() for character in self.password):
            raise ValueError("Password must contain letters and numbers")
        return self


def _is_initialized(db: Session) -> bool:
    return db.query(User.id).filter(User.role == "super_admin").first() is not None


def _write_environment(values: dict[str, str]) -> None:
    existing = _ENV_PATH.read_text(encoding="utf-8") if _ENV_PATH.exists() else ""
    lines = existing.splitlines()
    remaining_keys = set(values)
    updated_lines: list[str] = []
    for line in lines:
        key, separator, _ = line.partition("=")
        if separator and key.strip() in values:
            normalized_key = key.strip()
            updated_lines.append(f"{normalized_key}={values[normalized_key]}")
            remaining_keys.discard(normalized_key)
        else:
            updated_lines.append(line)
    updated_lines.extend(f"{key}={values[key]}" for key in sorted(remaining_keys))
    temporary_path = _ENV_PATH.with_suffix(".env.tmp")
    temporary_path.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")
    os.replace(temporary_path, _ENV_PATH)


@router.get("/status")
def setup_status(db: Session = Depends(get_db)):
    initialized = _is_initialized(db)
    return {
        "is_initialized": initialized,
        "db_status": "ready",
        "needs_setup": not initialized,
    }


@router.post("/test-db")
def test_database_connection(database: DatabaseConfig):
    candidate_engine = None
    try:
        candidate_engine = create_engine(database.url(), future=True)
        with candidate_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"success": True, "message": "Database connection succeeded"}
    except Exception as exc:
        return {"success": False, "message": str(exc)}
    finally:
        if candidate_engine is not None:
            candidate_engine.dispose()


@router.post("/initialize", status_code=status.HTTP_201_CREATED)
def initialize_system(payload: InitializeRequest, db: Session = Depends(get_db)):
    with _initialization_lock:
        if _is_initialized(db):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System has already been initialized")

        ai_provider = "google_ai_studio" if payload.ai_provider == "gemini" else payload.ai_provider
        db_url = payload.database.url()
        environment = {
            "DB_URL": db_url,
            "APP_NAME": payload.app_name,
            "AI_PROVIDER": ai_provider,
            "SCRAPING_INTERVAL_SECONDS": str(payload.monitoring_interval_minutes * 60),
        }
        if ai_provider == "google_ai_studio" and payload.ai_api_key:
            environment["GOOGLE_AI_STUDIO_API_KEY"] = payload.ai_api_key
        if ai_provider == "openrouter" and payload.ai_api_key:
            environment["OPENROUTER_API_KEY"] = payload.ai_api_key
        if ai_provider == "custom_openai" and payload.ai_api_key:
            environment["CUSTOM_OPENAI_API_KEY"] = payload.ai_api_key

        try:
            database_session.configure_database(db_url)
            Base.metadata.create_all(bind=database_session.engine)
            migrate_topic_schema()
            setup_db = database_session.SessionLocal()
            try:
                if _is_initialized(setup_db):
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System has already been initialized")
                administrator = User(
                    email=payload.email_or_username,
                    hashed_password=hash_password(payload.password),
                    full_name=payload.full_name,
                    role="super_admin",
                    is_active=True,
                )
                setup_db.add(administrator)
                setup_db.flush()
                topic = setup_db.query(Topic).filter(Topic.title == "General Monitoring").first()
                if topic is None:
                    topic = Topic(title="General Monitoring", description="المراقبة العامة", created_by_id=administrator.id)
                    setup_db.add(topic)
                    setup_db.flush()
                elif topic.created_by_id is None:
                    topic.created_by_id = administrator.id
                if setup_db.get(UserTopic, (administrator.id, topic.id)) is None:
                    setup_db.add(UserTopic(user_id=administrator.id, topic_id=topic.id, role="topic_admin"))
                record_audit(
                    setup_db,
                    user_id=administrator.id,
                    topic_id=topic.id,
                    action="SYSTEM_INITIALIZED",
                    entity_type="system",
                    details={"app_name": payload.app_name, "ai_provider": ai_provider},
                )
                setup_db.commit()
                _write_environment(environment)
            except Exception:
                setup_db.rollback()
                raise
            finally:
                setup_db.close()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Initialization failed: {exc}") from exc

        access_token = create_access_token({"sub": str(administrator.id), "email": administrator.email, "role": administrator.role})
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": administrator.id,
            "email": administrator.email,
            "full_name": administrator.full_name,
            "role": administrator.role,
        }