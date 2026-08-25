"""Topic-centric resources and role-based access control endpoints."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.core.deps import get_current_admin_user, get_current_topic_admin, get_current_topic_user, get_current_user
from app.core.security import hash_password
from app.db.session import get_db
from app.models import Keyword, MonitoredSource, Post, Topic, User, UserTopic

router = APIRouter(prefix="/api/v1/topics", tags=["Topics"])


class TopicInput(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None


class TopicOutput(TopicInput):
    id: int
    created_by_id: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssignmentInput(BaseModel):
    user_id: int
    role: str


class SourceInput(BaseModel):
    platform: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    url_or_handle: str = Field(min_length=1, max_length=500)
    target_type: str = Field(default="url", max_length=30)
    apify_actor_id: str | None = Field(default=None, max_length=255)
    is_active: bool = True

    @field_validator("platform", "target_type", "url_or_handle", mode="before")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join(str(value).strip().split())

    @field_validator("url_or_handle")
    @classmethod
    def validate_target(cls, value: str, info):
        platform = str(info.data.get("platform", "")).lower()
        if any(character in value for character in ("\r", "\n", "\x00")):
            raise ValueError("Target contains invalid control characters")
        is_handle = platform in {"reddit", "facebook", "instagram", "x", "twitter"} and not value.startswith(("http://", "https://"))
        if not is_handle and not value.startswith(("http://", "https://")):
            raise ValueError("Target must be an HTTP(S) URL for this platform")
        if not is_handle:
            parsed = urlsplit(value)
            if not parsed.netloc or not parsed.hostname:
                raise ValueError("Target must include a valid hostname")
        if "@" in value.split("//", 1)[-1].split("/", 1)[0]:
            raise ValueError("Target URLs must not contain credentials")
        return value


class SourceOutput(SourceInput):
    id: int
    topic_id: int
    last_scraped_at: datetime | None = None
    status: str

    model_config = ConfigDict(from_attributes=True)


class KeywordInput(BaseModel):
    word_or_phrase: str = Field(min_length=1, max_length=500)
    category: str = Field(default="general", min_length=1, max_length=100)
    is_active: bool = True


class KeywordOutput(KeywordInput):
    id: int
    topic_id: int

    model_config = ConfigDict(from_attributes=True)


class NewsOutput(BaseModel):
    id: int
    topic_id: int
    source_id: int
    platform: str
    author: str
    content: str
    published_at: datetime
    scraped_at: datetime
    severity_level: str | None

    model_config = ConfigDict(from_attributes=True)


@router.post("", response_model=TopicOutput, status_code=status.HTTP_201_CREATED)
def create_topic(
    topic_data: TopicInput,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
) -> Topic:
    topic = Topic(**topic_data.model_dump(), created_by_id=_.id)
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return topic


@router.get("", response_model=list[TopicOutput])
def list_topics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Topic]:
    if current_user.role == "super_admin":
        return db.query(Topic).order_by(Topic.created_at.desc()).all()
    return db.query(Topic).join(UserTopic).filter(UserTopic.user_id == current_user.id).all()


@router.put("/{topic_id}", response_model=TopicOutput)
def update_topic(topic_id: int, topic_data: TopicInput, db: Session = Depends(get_db), _: User = Depends(get_current_admin_user)):
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    topic.title = topic_data.title
    topic.description = topic_data.description
    db.commit()
    db.refresh(topic)
    return topic


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_topic(topic_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_admin_user)):
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    db.delete(topic)
    db.commit()


@router.post("/{topic_id}/assign-user", status_code=status.HTTP_201_CREATED)
def assign_user(
    topic_id: int,
    assignment_data: AssignmentInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_topic_admin),
):
    if assignment_data.role not in ("topic_admin", "topic_monitor"):
        raise HTTPException(status_code=400, detail="Role must be topic_admin or topic_monitor")
    if current_user.role != "super_admin" and assignment_data.role != "topic_monitor":
        raise HTTPException(status_code=403, detail="Topic admins may assign only topic monitors")
    if db.query(Topic).filter(Topic.id == topic_id).first() is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    if db.query(User).filter(User.id == assignment_data.user_id).first() is None:
        raise HTTPException(status_code=404, detail="User not found")
    existing = db.query(UserTopic).filter(
        UserTopic.user_id == assignment_data.user_id,
        UserTopic.topic_id == topic_id,
    ).first()
    if existing:
        existing.role = assignment_data.role
    else:
        db.add(UserTopic(user_id=assignment_data.user_id, topic_id=topic_id, role=assignment_data.role))
    db.commit()
    return {"topic_id": topic_id, "user_id": assignment_data.user_id, "role": assignment_data.role}


@router.get("/{topic_id}/sources", response_model=list[SourceOutput])
def list_sources(topic_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_topic_user)):
    return db.query(MonitoredSource).filter(MonitoredSource.topic_id == topic_id).order_by(MonitoredSource.created_at.desc()).all()


@router.post("/{topic_id}/sources", response_model=SourceOutput, status_code=status.HTTP_201_CREATED)
def create_source(topic_id: int, source: SourceInput, db: Session = Depends(get_db), _: User = Depends(get_current_topic_admin)):
    if db.query(Topic).filter(Topic.id == topic_id).first() is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    record = MonitoredSource(topic_id=topic_id, status="active", **source.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.put("/{topic_id}/sources/{source_id}", response_model=SourceOutput)
def update_source(topic_id: int, source_id: int, source: SourceInput, db: Session = Depends(get_db), _: User = Depends(get_current_topic_admin)):
    record = db.query(MonitoredSource).filter(MonitoredSource.id == source_id, MonitoredSource.topic_id == topic_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Source not found")
    for key, value in source.model_dump().items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/{topic_id}/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(topic_id: int, source_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_topic_admin)):
    record = db.query(MonitoredSource).filter(MonitoredSource.id == source_id, MonitoredSource.topic_id == topic_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Source not found")
    db.delete(record)
    db.commit()


@router.patch("/{topic_id}/sources/{source_id}/toggle", response_model=SourceOutput)
def toggle_source(topic_id: int, source_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_topic_admin)):
    record = db.query(MonitoredSource).filter(MonitoredSource.id == source_id, MonitoredSource.topic_id == topic_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Source not found")
    record.is_active = not record.is_active
    record.status = "active" if record.is_active else "disabled"
    db.commit()
    db.refresh(record)
    return record


@router.get("/{topic_id}/keywords", response_model=list[KeywordOutput])
def list_keywords(topic_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_topic_user)):
    return db.query(Keyword).filter(Keyword.topic_id == topic_id).order_by(Keyword.created_at.desc()).all()


@router.post("/{topic_id}/keywords", response_model=KeywordOutput, status_code=status.HTTP_201_CREATED)
def create_keyword(topic_id: int, keyword: KeywordInput, db: Session = Depends(get_db), _: User = Depends(get_current_topic_admin)):
    if db.query(Topic).filter(Topic.id == topic_id).first() is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    record = Keyword(topic_id=topic_id, **keyword.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.put("/{topic_id}/keywords/{keyword_id}", response_model=KeywordOutput)
def update_keyword(topic_id: int, keyword_id: int, keyword: KeywordInput, db: Session = Depends(get_db), _: User = Depends(get_current_topic_admin)):
    record = db.query(Keyword).filter(Keyword.id == keyword_id, Keyword.topic_id == topic_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Keyword not found")
    for key, value in keyword.model_dump().items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/{topic_id}/keywords/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_keyword(topic_id: int, keyword_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_topic_admin)):
    record = db.query(Keyword).filter(Keyword.id == keyword_id, Keyword.topic_id == topic_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Keyword not found")
    db.delete(record)
    db.commit()


@router.get("/{topic_id}/news", response_model=list[NewsOutput])
def list_news(
    topic_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_topic_user),
):
    return db.query(Post).filter(Post.topic_id == topic_id).order_by(Post.published_at.desc()).offset(skip).limit(limit).all()


@router.get("/{topic_id}/stats")
def topic_stats(topic_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_topic_user)):
    return {
        "topic_id": topic_id,
        "sources_count": db.query(MonitoredSource).filter(MonitoredSource.topic_id == topic_id).count(),
        "keywords_count": db.query(Keyword).filter(Keyword.topic_id == topic_id).count(),
        "news_count": db.query(Post).filter(Post.topic_id == topic_id).count(),
    }