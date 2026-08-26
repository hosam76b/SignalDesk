"""Topic-scoped audit activity endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.deps import get_current_topic_user
from app.db.session import get_db
from app.models import AuditLog, User

router = APIRouter(prefix="/api/v1/audit-logs", tags=["Audit Logs"])


class AuditOutput(BaseModel):
    id: int
    user_id: int | None
    topic_id: int | None
    post_id: int | None
    action: str
    entity_type: str
    details: dict | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


@router.get("/topics/{topic_id}", response_model=list[AuditOutput])
def list_topic_audit_logs(
    topic_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_topic_user),
):
    return db.query(AuditLog).filter(AuditLog.topic_id == topic_id).order_by(AuditLog.created_at.desc()).limit(limit).all()