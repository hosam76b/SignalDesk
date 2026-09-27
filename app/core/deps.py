"""Shared FastAPI dependencies for authentication and database access."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models.topic import UserTopic
from app.models.user import User


security = HTTPBearer()


ROLE_ALIASES = {
    "admin": "super_admin",
    "analyst": "analyst",
    "observer": "observer",
    "topic_admin": "topic_manager",
    "topic_manager": "topic_manager",
    "topic_monitor": "analyst",
    "super_admin": "super_admin",
}


def normalize_role(role: str | None) -> str:
    if role is None:
        return "observer"
    normalized = str(role).strip().lower()
    if "." in normalized:
        normalized = normalized.split(".")[-1]
    return ROLE_ALIASES.get(normalized, normalized)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user from a JWT bearer token."""
    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("sub") is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")
    user.role = normalize_role(user.role)
    return user


def get_current_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Resolve the authenticated user and require the administrator role."""
    if normalize_role(current_user.role) != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required",
        )
    return current_user


def get_current_topic_user(
    topic_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Require a super admin or an assignment to the requested topic."""
    if normalize_role(current_user.role) == "super_admin":
        return current_user

    assignment = db.query(UserTopic).filter(
        UserTopic.user_id == current_user.id,
        UserTopic.topic_id == topic_id,
    ).first()
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this topic",
        )
    return current_user


def get_current_topic_admin(
    topic_id: int,
    current_user: User = Depends(get_current_topic_user),
    db: Session = Depends(get_db),
) -> User:
    """Require super-admin or topic-admin access to the requested topic.

    A topic monitor is deliberately excluded: ``normalize_role`` folds
    ``topic_monitor`` into ``analyst``, so listing it here would hand monitors
    exactly the create/update/delete rights over sources, keywords, and topic
    membership that this gate exists to withhold. Monitors keep read access via
    ``get_current_topic_user``.
    """
    if normalize_role(current_user.role) == "super_admin":
        return current_user

    assignment = db.query(UserTopic).filter(
        UserTopic.user_id == current_user.id,
        UserTopic.topic_id == topic_id,
    ).first()
    allowed_roles = {"topic_manager", "topic_admin"}
    if assignment is None or normalize_role(assignment.role) not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Topic administrator privileges required",
        )
    return current_user


def require_role(*allowed_roles: str):
    """Dependency factory: require the current user's normalized role to be one of `allowed_roles`."""
    normalized_allowed = {normalize_role(role) for role in allowed_roles}

    def _check(current_user: User = Depends(get_current_user)) -> User:
        if normalize_role(current_user.role) not in normalized_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have the required role for this action",
            )
        return current_user

    return _check


def require_topic_access(*allowed_roles: str):
    """Dependency factory: require topic membership (or super admin), optionally restricted to specific topic roles."""
    normalized_allowed = {normalize_role(role) for role in allowed_roles} if allowed_roles else None

    def _check(
        topic_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if normalize_role(current_user.role) == "super_admin":
            return current_user

        assignment = db.query(UserTopic).filter(
            UserTopic.user_id == current_user.id,
            UserTopic.topic_id == topic_id,
        ).first()
        if assignment is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this topic",
            )
        if normalized_allowed is not None and normalize_role(assignment.role) not in normalized_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have the required topic role for this action",
            )
        return current_user

    return _check
