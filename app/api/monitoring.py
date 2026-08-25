"""CRUD endpoints for monitored sources and keyword rules."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_admin_user
from app.db.session import get_db
from app.models.keyword import Keyword
from app.models.source import MonitoredSource
from app.models.user import User

router = APIRouter(prefix="/api/monitoring", tags=["Monitoring Configuration"])


class SourceInput(BaseModel):
    """Source creation/update payload."""

    platform: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    url_or_handle: str = Field(min_length=1, max_length=500)
    is_active: bool = True


class SourceOutput(SourceInput):
    """Source response payload."""

    id: int
    topic_id: int
    last_scraped_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class KeywordInput(BaseModel):
    """Keyword creation/update payload."""

    word_or_phrase: str = Field(min_length=1, max_length=500)
    category: str = Field(default="general", min_length=1, max_length=100)
    is_active: bool = True


class KeywordOutput(KeywordInput):
    """Keyword response payload."""

    id: int
    topic_id: int

    model_config = ConfigDict(from_attributes=True)


@router.get("/sources", response_model=list[SourceOutput])
def list_sources(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
) -> list[MonitoredSource]:
    """List configured monitored sources."""
    return db.query(MonitoredSource).order_by(MonitoredSource.created_at.desc()).all()


@router.post("/sources", response_model=SourceOutput, status_code=status.HTTP_201_CREATED)
def create_source(
    source: SourceInput,
    topic_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
) -> MonitoredSource:
    """Create a monitored source."""
    record = MonitoredSource(topic_id=topic_id, status="active", **source.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.patch("/sources/{source_id}", response_model=SourceOutput)
def update_source(
    source_id: int,
    source: SourceInput,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
) -> MonitoredSource:
    """Update a monitored source."""
    record = db.query(MonitoredSource).filter(MonitoredSource.id == source_id).first()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    for key, value in source.model_dump().items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_source(
    source_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
) -> None:
    """Delete a monitored source and its posts through the FK cascade."""
    record = db.query(MonitoredSource).filter(MonitoredSource.id == source_id).first()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    db.delete(record)
    db.commit()


@router.get("/keywords", response_model=list[KeywordOutput])
def list_keywords(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
) -> list[Keyword]:
    """List configured keyword rules."""
    return db.query(Keyword).order_by(Keyword.created_at.desc()).all()


@router.post("/keywords", response_model=KeywordOutput, status_code=status.HTTP_201_CREATED)
def create_keyword(
    keyword: KeywordInput,
    topic_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
) -> Keyword:
    """Create a keyword rule."""
    existing = db.query(Keyword).filter(Keyword.word_or_phrase == keyword.word_or_phrase).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Keyword already exists")
    record = Keyword(topic_id=topic_id, **keyword.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.patch("/keywords/{keyword_id}", response_model=KeywordOutput)
def update_keyword(
    keyword_id: int,
    keyword: KeywordInput,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
) -> Keyword:
    """Update a keyword rule."""
    record = db.query(Keyword).filter(Keyword.id == keyword_id).first()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Keyword not found")
    for key, value in keyword.model_dump().items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/keywords/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_keyword(
    keyword_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
) -> None:
    """Delete a keyword rule."""
    record = db.query(Keyword).filter(Keyword.id == keyword_id).first()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Keyword not found")
    db.delete(record)
    db.commit()
