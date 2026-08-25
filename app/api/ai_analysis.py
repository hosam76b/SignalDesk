"""API endpoints for local Ollama content evaluation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.core.deps import get_current_user, get_current_admin_user
from app.services.ai_orchestrator import ai_orchestrator

router = APIRouter(prefix="/api/ai", tags=["AI Analysis"])


class AnalysisResponse(BaseModel):
    """Summary of a batch analysis operation."""

    success: bool
    processed: int
    analyzed: int
    updated: int
    failed: int
    errors: list[dict[str, Any]]
    duration_seconds: float


class FlaggedPostResponse(BaseModel):
    """Safe analyst-facing representation of an evaluated post."""

    id: int
    source: str
    source_id: int
    platform: str
    author: str
    content: str
    post_url: str | None
    published_at: str | None
    scraped_at: str | None
    severity_level: str
    violence_category: str | None
    ai_summary: str | None
    is_flagged: bool


class FlaggedPostsResponse(BaseModel):
    """Paginated flagged-post response."""

    success: bool
    total_count: int
    returned: int
    limit: int
    offset: int
    posts: list[FlaggedPostResponse]


@router.post("/analyze-pending", response_model=AnalysisResponse)
def analyze_pending_posts(
    batch_size: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
) -> AnalysisResponse:
    """Analyze one bounded batch of posts missing AI evaluation."""
    result = ai_orchestrator.process_unanalyzed_posts(db, batch_size=batch_size)
    return AnalysisResponse(**result)


@router.get("/flagged-posts", response_model=FlaggedPostsResponse)
def get_flagged_posts(
    severity: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FlaggedPostsResponse:
    """Retrieve flagged posts and posts with high or critical severity."""
    try:
        result = ai_orchestrator.get_flagged_posts(db, severity, limit, offset)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return FlaggedPostsResponse(**result)
