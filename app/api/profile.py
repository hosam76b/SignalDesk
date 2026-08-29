"""User profile, password self-service, and TOTP 2FA endpoints."""

from __future__ import annotations

import base64
import io
from datetime import datetime, timedelta, timezone

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, normalize_role
from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.models import AuditLog, User
from app.services.audit_service import record_audit

router = APIRouter(prefix="/api/v1/profile", tags=["Profile"])

TWO_FACTOR_ELIGIBLE_ROLES = {"super_admin", "topic_manager"}
VALID_ACTIVITY_ACTIONS = {
    "login",
    "proposal_submitted",
    "source_proposed",
    "keyword_proposed",
    "proposal_approved",
    "source_proposal_approved",
    "keyword_proposal_approved",
    "prompt_updated",
    "report_exported",
    "post_priority_updated",
}


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    avatar_url: str | None = Field(default=None, max_length=500)
    job_title: str | None = Field(default=None, max_length=255)


class ChangePasswordInput(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class ActivityEntry(BaseModel):
    id: int
    action: str
    entity_type: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProfileOutput(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    avatar_url: str | None
    job_title: str | None
    last_login_at: datetime | None
    password_changed_at: datetime
    totp_enabled: bool
    two_factor_eligible: bool
    activity_score: str
    activity_count_30d: int
    recent_activity: list[ActivityEntry]

    model_config = ConfigDict(from_attributes=True)


def _activity_score(count: int) -> str:
    if count >= 20:
        return "high"
    if count >= 5:
        return "medium"
    return "low"


def _build_profile(db: Session, user: User) -> ProfileOutput:
    since = datetime.now(timezone.utc) - timedelta(days=30)
    recent = (
        db.query(AuditLog)
        .filter(AuditLog.user_id == user.id, AuditLog.created_at >= since)
        .order_by(AuditLog.created_at.desc())
        .limit(15)
        .all()
    )
    valid_count = sum(1 for entry in recent if entry.action in VALID_ACTIVITY_ACTIONS)
    return ProfileOutput(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=normalize_role(user.role),
        avatar_url=user.avatar_url,
        job_title=user.job_title,
        last_login_at=user.last_login_at,
        password_changed_at=user.password_changed_at,
        totp_enabled=user.totp_enabled,
        two_factor_eligible=normalize_role(user.role) in TWO_FACTOR_ELIGIBLE_ROLES,
        activity_score=_activity_score(valid_count),
        activity_count_30d=valid_count,
        recent_activity=recent,
    )


@router.get("/me", response_model=ProfileOutput)
def get_my_profile(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _build_profile(db, current_user)


@router.patch("/me", response_model=ProfileOutput)
def update_my_profile(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    if payload.avatar_url is not None:
        current_user.avatar_url = payload.avatar_url
    if payload.job_title is not None:
        current_user.job_title = payload.job_title
    db.commit()
    db.refresh(current_user)
    return _build_profile(db, current_user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_my_password(
    payload: ChangePasswordInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")
    current_user.hashed_password = hash_password(payload.new_password)
    current_user.password_changed_at = datetime.now(timezone.utc)
    record_audit(
        db,
        user_id=current_user.id,
        action="password_changed",
        entity_type="user",
        details={},
    )
    db.commit()


@router.post("/2fa/setup")
def setup_two_factor(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Generate a TOTP secret and QR code; the secret is not activated until /2fa/enable succeeds."""
    if normalize_role(current_user.role) not in TWO_FACTOR_ELIGIBLE_ROLES:
        raise HTTPException(status_code=403, detail="2FA is only available for topic managers and super admins")
    secret = pyotp.random_base32()
    current_user.totp_secret = secret
    current_user.totp_enabled = False
    db.commit()

    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=current_user.email, issuer_name="Signaldesk")
    image = qrcode.make(uri)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {"secret": secret, "provisioning_uri": uri, "qr_code_base64": f"data:image/png;base64,{qr_base64}"}


class TwoFactorCodeInput(BaseModel):
    code: str = Field(min_length=6, max_length=6)


@router.post("/2fa/enable", status_code=status.HTTP_204_NO_CONTENT)
def enable_two_factor(
    payload: TwoFactorCodeInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="Call /2fa/setup first")
    if not pyotp.totp.TOTP(current_user.totp_secret).verify(payload.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid verification code")
    current_user.totp_enabled = True
    record_audit(db, user_id=current_user.id, action="2fa_enabled", entity_type="user", details={})
    db.commit()


@router.post("/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
def disable_two_factor(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    current_user.totp_enabled = False
    current_user.totp_secret = None
    record_audit(db, user_id=current_user.id, action="2fa_disabled", entity_type="user", details={})
    db.commit()
