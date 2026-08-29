"""Cross-topic review endpoints for observer-submitted source/keyword proposals."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, normalize_role
from app.db.session import get_db
from app.models import Keyword, MonitoredSource, User, UserTopic
from app.services.audit_service import record_audit

router = APIRouter(prefix="/api/v1/approvals", tags=["Approvals"])


class ApprovalDecisionInput(BaseModel):
    status: str  # "approved" or "rejected"


def _require_topic_admin(db: Session, current_user: User, topic_id: int) -> None:
    """Raise 403 unless the current user is a super admin or manager/admin for `topic_id`."""
    if normalize_role(current_user.role) == "super_admin":
        return
    assignment = db.query(UserTopic).filter(
        UserTopic.user_id == current_user.id,
        UserTopic.topic_id == topic_id,
    ).first()
    allowed_roles = {"topic_manager", "topic_admin", "topic_monitor", "analyst"}
    if assignment is None or normalize_role(assignment.role) not in allowed_roles:
        raise HTTPException(status_code=403, detail="Topic administrator privileges required")


@router.patch("/sources/{source_id}")
def review_source_proposal(
    source_id: int,
    decision: ApprovalDecisionInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if decision.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Status must be 'approved' or 'rejected'")
    record = db.query(MonitoredSource).filter(MonitoredSource.id == source_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Source proposal not found")
    _require_topic_admin(db, current_user, record.topic_id)

    record.approval_status = decision.status
    record.is_active = decision.status == "approved"
    record.status = "active" if decision.status == "approved" else "disabled"
    record.reviewed_by_id = current_user.id
    record.reviewed_at = datetime.now(timezone.utc)
    record_audit(
        db,
        user_id=current_user.id,
        topic_id=record.topic_id,
        action=f"source_proposal_{decision.status}",
        entity_type="monitored_source",
        details={"source_id": record.id},
    )
    db.commit()
    db.refresh(record)
    return record


@router.patch("/keywords/{keyword_id}")
def review_keyword_proposal(
    keyword_id: int,
    decision: ApprovalDecisionInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if decision.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Status must be 'approved' or 'rejected'")
    record = db.query(Keyword).filter(Keyword.id == keyword_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Keyword proposal not found")
    _require_topic_admin(db, current_user, record.topic_id)

    record.approval_status = decision.status
    record.is_active = decision.status == "approved"
    record.reviewed_by_id = current_user.id
    record.reviewed_at = datetime.now(timezone.utc)
    record_audit(
        db,
        user_id=current_user.id,
        topic_id=record.topic_id,
        action=f"keyword_proposal_{decision.status}",
        entity_type="keyword",
        details={"keyword_id": record.id},
    )
    db.commit()
    db.refresh(record)
    return record
