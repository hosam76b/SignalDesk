"""
Authentication API endpoints.
Handles user login, token generation, and current user retrieval with database integration.
"""

from fastapi import APIRouter, HTTPException, Depends, status, Request, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from datetime import datetime, timedelta, timezone

from app.db.session import get_db
from app.models.user import User
from app.core.deps import get_current_user
from app.core.rate_limit import limiter, AUTH_RATE_LIMIT
from app.services.audit_service import record_audit
from app.services.email import send_password_reset_email
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
    create_password_reset_token,
    verify_password_reset_token,
)
from config import settings

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ============================================================================
# Pydantic Models (Request/Response)
# ============================================================================

class LoginRequest(BaseModel):
    """Request model for login endpoint."""

    email: str
    password: str
    totp_code: str | None = None

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "email": "admin@example.com",
                "password": "admin123"
            }
        })


class TokenResponse(BaseModel):
    """Response model for login endpoint."""

    access_token: str
    token_type: str
    user_id: int
    email: str
    full_name: str
    role: str

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "user_id": 1,
                "email": "admin@example.com",
                "full_name": "Administrator",
                "role": "super_admin"
            }
        })


class UserResponse(BaseModel):
    """Response model for user information."""

    id: int
    email: str
    full_name: str
    role: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True, json_schema_extra={
            "example": {
                "id": 1,
                "email": "admin@example.com",
                "full_name": "Administrator",
                "role": "super_admin",
                "is_active": True
            }
        })


# ============================================================================
# Dependency Functions
# ============================================================================

# ============================================================================
# Authentication Endpoints
# ============================================================================

@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
@limiter.limit(AUTH_RATE_LIMIT)
async def login(request: Request, credentials: LoginRequest, db: Session = Depends(get_db)):
    """
    User login endpoint.
    Authenticates user by email and password, returns JWT token.

    Args:
        credentials (LoginRequest): Email and password.
        db (Session): Database session.

    Returns:
        TokenResponse: JWT token and user information.

    Raises:
        HTTPException: If credentials are invalid or user is inactive.
    """
    # Find user by email
    user = db.query(User).filter(User.email == credentials.email).first()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    if user.totp_enabled:
        import pyotp
        if not credentials.totp_code or not pyotp.totp.TOTP(user.totp_secret).verify(credentials.totp_code, valid_window=1):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Valid 2FA code required"
            )

    # Create JWT token
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role
    }
    access_token = create_access_token(data=token_data, expires_delta=access_token_expires)

    user.last_login_at = datetime.now(timezone.utc)
    record_audit(db, user_id=user.id, action="login", entity_type="user", details={})
    db.commit()

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role
    )


@router.get("/me", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def get_me(
    current_user: User = Depends(get_current_user),
):
    """
    Get current authenticated user information.
    Requires valid JWT token in Authorization header.

    Args:
        current_user (User): Current authenticated user (from dependency).

    Returns:
        UserResponse: User profile information.
    """
    return UserResponse.model_validate(current_user)


# ============================================================================
# Password Reset Workflow
# ============================================================================

class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(AUTH_RATE_LIMIT)
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Issue a signed, 15-minute, single-use reset token and email it asynchronously.

    Always returns 202 regardless of whether the email exists, to avoid account enumeration.
    """
    user = db.query(User).filter(User.email == payload.email).first()
    if user is not None and user.is_active:
        reset_token = create_password_reset_token(user.id, user.password_changed_at)
        background_tasks.add_task(send_password_reset_email, user.email, user.full_name, reset_token)
    return {"message": "If that email exists, a password reset link has been sent."}


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(AUTH_RATE_LIMIT)
async def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    """Validate a password reset token and set the new password. The token is single-use."""
    # The token is scoped to a user id, but we must locate the user before verifying
    # since verification is bound to that user's current password_changed_at timestamp.
    raw = decode_token(payload.token)
    if raw is None or raw.get("type") != "password_reset" or raw.get("sub") is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    try:
        user_id = int(raw["sub"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    verified_id = verify_password_reset_token(payload.token, user.password_changed_at)
    if verified_id != user.id:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user.hashed_password = hash_password(payload.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    record_audit(db, user_id=user.id, action="password_reset", entity_type="user", details={})
    db.commit()
