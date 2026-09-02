"""Topic-centric resources and role-based access control endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_admin_user, get_current_topic_admin, get_current_topic_user, get_current_user
from app.core.security import hash_password
from app.db.session import get_db
from app.models import AuditLog, Keyword, MonitoredSource, Post, Topic, User, UserTopic
from app.services.audit_service import record_audit
from app.services.pdf_report_service import generate_topic_executive_pdf
from app.services.propagation_service import analyze_topic_propagation_graph
from app.services.scraper_service import SUPPORTED_PLATFORMS

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


class TopicMemberOutput(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class SourceInput(BaseModel):
    platform: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    url_or_handle: str = Field(min_length=1, max_length=500)
    target_type: str = Field(default="url", max_length=30)
    apify_actor_id: str | None = Field(default=None, max_length=255)
    is_active: bool = True

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in SUPPORTED_PLATFORMS:
            raise ValueError(f"Unsupported platform: {normalized}")
        return normalized

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
        is_handle = platform in {"reddit", "facebook", "instagram", "x", "twitter", "telegram"} and not value.startswith(("http://", "https://"))
        if not is_handle and not value.startswith(("http://", "https://")):
            raise ValueError("Target must be an HTTP(S) URL for this platform")
        if not is_handle:
            parsed = urlsplit(value)
            if not parsed.netloc or not parsed.hostname:
                raise ValueError("Target must include a valid hostname")
        if "@" in value.split("//", 1)[-1].split("/", 1)[0]:
            raise ValueError("Target URLs must not contain credentials")
        return value


class SourceOutput(BaseModel):
    """Read-only projection of MonitoredSource; deliberately unvalidated so synthetic
    rows (e.g. the "Quick Ingest" platform="upload" bookkeeping source) still serialize."""
    id: int
    platform: str
    name: str
    url_or_handle: str
    target_type: str
    apify_actor_id: str | None = None
    is_active: bool
    last_scraped_at: datetime | None = None
    status: str
    last_error: str | None = None
    last_error_at: datetime | None = None
    approval_status: str = "approved"
    proposed_by_id: int | None = None
    reviewed_by_id: int | None = None
    reviewed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class KeywordInput(BaseModel):
    word_or_phrase: str = Field(min_length=1, max_length=500)
    category: str = Field(default="general", min_length=1, max_length=100)
    is_active: bool = True


class KeywordOutput(KeywordInput):
    id: int
    topic_id: int
    approval_status: str = "approved"
    proposed_by_id: int | None = None
    reviewed_by_id: int | None = None
    reviewed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ApprovalsSummary(BaseModel):
    sources: list[SourceOutput]
    keywords: list[KeywordOutput]


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
    is_important: bool
    is_dangerous: bool

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


@router.get("/{topic_id}/users", response_model=list[TopicMemberOutput])
def list_topic_users(topic_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_topic_admin)):
    return db.query(User).join(UserTopic).filter(UserTopic.topic_id == topic_id).order_by(User.full_name).all()


@router.get("/{topic_id}/available-users", response_model=list[TopicMemberOutput])
def list_available_topic_users(topic_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_topic_admin)):
    assigned_ids = db.query(UserTopic.user_id).filter(UserTopic.topic_id == topic_id)
    return db.query(User).filter(
        User.role == "topic_monitor",
        User.is_active.is_(True),
        ~User.id.in_(assigned_ids),
    ).order_by(User.full_name).all()


@router.delete("/{topic_id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_topic_user(topic_id: int, user_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_topic_admin)):
    assignment = db.query(UserTopic).filter(
        UserTopic.topic_id == topic_id,
        UserTopic.user_id == user_id,
    ).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Topic assignment not found")
    if assignment.role == "topic_admin" and _.role != "super_admin":
        raise HTTPException(status_code=403, detail="Only SuperAdmin can remove a topic administrator")
    db.delete(assignment)
    db.commit()


@router.get("/{topic_id}/sources", response_model=list[SourceOutput])
def list_sources(topic_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_topic_user)):
    # Exclude the synthetic "Quick Ingest" bookkeeping source; it exists only to
    # satisfy the FK on quick-ingested posts, not for recurring scraping.
    return db.query(MonitoredSource).filter(MonitoredSource.name != "Quick Ingest").order_by(MonitoredSource.created_at.desc()).all()


@router.post("/{topic_id}/sources", response_model=SourceOutput, status_code=status.HTTP_201_CREATED)
def create_source(topic_id: int, source: SourceInput, db: Session = Depends(get_db), current_user: User = Depends(get_current_topic_admin)):
    if db.query(Topic).filter(Topic.id == topic_id).first() is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    existing = db.query(MonitoredSource).filter(
        func.lower(MonitoredSource.url_or_handle) == source.url_or_handle.lower()
    ).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Source URL or handle already exists")
    record = MonitoredSource(
        status="active",
        approval_status="approved",
        proposed_by_id=current_user.id,
        reviewed_by_id=current_user.id,
        reviewed_at=datetime.now(timezone.utc),
        **source.model_dump(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.put("/{topic_id}/sources/{source_id}", response_model=SourceOutput)
def update_source(topic_id: int, source_id: int, source: SourceInput, db: Session = Depends(get_db), _: User = Depends(get_current_topic_admin)):
    record = db.query(MonitoredSource).filter(MonitoredSource.id == source_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Source not found")
    existing = db.query(MonitoredSource).filter(
        MonitoredSource.id != source_id,
        func.lower(MonitoredSource.url_or_handle) == source.url_or_handle.lower(),
    ).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Source URL or handle already exists")
    for key, value in source.model_dump().items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/{topic_id}/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(topic_id: int, source_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_topic_admin)):
    record = db.query(MonitoredSource).filter(MonitoredSource.id == source_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Source not found")
    db.delete(record)
    db.commit()


@router.patch("/{topic_id}/sources/{source_id}/toggle", response_model=SourceOutput)
def toggle_source(topic_id: int, source_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_topic_admin)):
    record = db.query(MonitoredSource).filter(MonitoredSource.id == source_id).first()
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
def create_keyword(topic_id: int, keyword: KeywordInput, db: Session = Depends(get_db), current_user: User = Depends(get_current_topic_admin)):
    if db.query(Topic).filter(Topic.id == topic_id).first() is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    record = Keyword(
        topic_id=topic_id,
        approval_status="approved",
        proposed_by_id=current_user.id,
        reviewed_by_id=current_user.id,
        reviewed_at=datetime.now(timezone.utc),
        **keyword.model_dump(),
    )
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


@router.post("/{topic_id}/proposals/sources", response_model=SourceOutput, status_code=status.HTTP_201_CREATED)
def propose_source(
    topic_id: int,
    source: SourceInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_topic_user),
):
    """Observer/analyst proposal for a new monitored source; requires manager approval before activation."""
    if db.query(Topic).filter(Topic.id == topic_id).first() is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    existing = db.query(MonitoredSource).filter(
        func.lower(MonitoredSource.url_or_handle) == source.url_or_handle.lower()
    ).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Source URL or handle already exists")
    payload = source.model_dump()
    payload["is_active"] = False
    record = MonitoredSource(
        status="pending_review",
        approval_status="pending",
        proposed_by_id=current_user.id,
        **payload,
    )
    db.add(record)
    record_audit(
        db,
        user_id=current_user.id,
        topic_id=topic_id,
        action="source_proposed",
        entity_type="monitored_source",
        details={"name": source.name, "platform": source.platform},
    )
    db.commit()
    db.refresh(record)
    return record


@router.post("/{topic_id}/proposals/keywords", response_model=KeywordOutput, status_code=status.HTTP_201_CREATED)
def propose_keyword(
    topic_id: int,
    keyword: KeywordInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_topic_user),
):
    """Observer/analyst proposal for a new keyword; requires manager approval before activation."""
    if db.query(Topic).filter(Topic.id == topic_id).first() is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    payload = keyword.model_dump()
    payload["is_active"] = False
    record = Keyword(
        topic_id=topic_id,
        approval_status="pending",
        proposed_by_id=current_user.id,
        **payload,
    )
    db.add(record)
    record_audit(
        db,
        user_id=current_user.id,
        topic_id=topic_id,
        action="keyword_proposed",
        entity_type="keyword",
        details={"word_or_phrase": keyword.word_or_phrase},
    )
    db.commit()
    db.refresh(record)
    return record


@router.get("/{topic_id}/approvals", response_model=ApprovalsSummary)
def list_pending_approvals(
    topic_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_topic_admin),
):
    """List pending source/keyword proposals awaiting a topic manager's decision."""
    sources = db.query(MonitoredSource).filter(
        MonitoredSource.approval_status == "pending",
    ).order_by(MonitoredSource.created_at.desc()).all()
    keywords = db.query(Keyword).filter(
        Keyword.topic_id == topic_id,
        Keyword.approval_status == "pending",
    ).order_by(Keyword.created_at.desc()).all()
    return ApprovalsSummary(sources=sources, keywords=keywords)


@router.get("/{topic_id}/my-proposals", response_model=ApprovalsSummary)
def list_my_proposals(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_topic_user),
):
    """Status tracking panel for the current user's own submitted proposals."""
    sources = db.query(MonitoredSource).filter(
        MonitoredSource.proposed_by_id == current_user.id,
    ).order_by(MonitoredSource.created_at.desc()).all()
    keywords = db.query(Keyword).filter(
        Keyword.topic_id == topic_id,
        Keyword.proposed_by_id == current_user.id,
    ).order_by(Keyword.created_at.desc()).all()
    return ApprovalsSummary(sources=sources, keywords=keywords)


@router.get("/{topic_id}/news", response_model=list[NewsOutput])
def list_news(
    topic_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_topic_user),
):
    return db.query(Post).filter(Post.topic_id == topic_id).order_by(Post.published_at.desc()).offset(skip).limit(limit).all()


class PriorityInput(BaseModel):
    is_important: bool = False
    is_dangerous: bool = False


@router.patch("/{topic_id}/news/{post_id}/priority", response_model=NewsOutput)
def update_news_priority(
    topic_id: int,
    post_id: int,
    priority: PriorityInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_topic_user),
):
    post = db.query(Post).filter(Post.id == post_id, Post.topic_id == topic_id).first()
    if post is None:
        raise HTTPException(status_code=404, detail="News item not found")
    post.is_important = priority.is_important
    post.is_dangerous = priority.is_dangerous
    record_audit(
        db,
        user_id=current_user.id,
        topic_id=topic_id,
        post_id=post_id,
        action="post_priority_updated",
        entity_type="post",
        details={"is_important": post.is_important, "is_dangerous": post.is_dangerous},
    )
    db.commit()
    db.refresh(post)
    return post


@router.get("/{topic_id}/stats")
def topic_stats(topic_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_topic_user)):
    return {
        "topic_id": topic_id,
        "sources_count": db.query(MonitoredSource).count(),
        "keywords_count": db.query(Keyword).filter(Keyword.topic_id == topic_id).count(),
        "news_count": db.query(Post).filter(Post.topic_id == topic_id).count(),
    }


@router.get("/{topic_id}/export-pdf")
@router.get("/{topic_id}/report.pdf", include_in_schema=False)
def export_topic_pdf_report(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_topic_user),
):
    """Generate and download Executive Intelligence PDF Report for this topic."""
    try:
        pdf_bytes = generate_topic_executive_pdf(db, topic_id, requester=current_user)
        filename = f"intelligence_report_topic_{topic_id}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"
        record_audit(
            db,
            user_id=current_user.id,
            topic_id=topic_id,
            action="report_exported",
            entity_type="report",
            details={"filename": filename},
        )
        db.commit()
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}") from exc


@router.get("/{topic_id}/propagation-graph")
def topic_propagation_graph(
    topic_id: int,
    cib_window_minutes: int = Query(default=60, ge=1, le=1440),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_topic_user),
):
    """Retrieve network propagation graph and CIB spread analysis for this topic."""
    return analyze_topic_propagation_graph(db, topic_id, cib_window_minutes=cib_window_minutes)
