"""Audit logging helpers."""

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def record_audit(
    db: Session,
    *,
    user_id: int | None,
    action: str,
    entity_type: str,
    topic_id: int | None = None,
    post_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    log = AuditLog(
        user_id=user_id,
        topic_id=topic_id,
        post_id=post_id,
        action=action,
        entity_type=entity_type,
        details=details or {},
    )
    db.add(log)
    return log
