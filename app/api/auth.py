"""
Authentication API endpoints.
Handles user login, token generation, and current user retrieval with database integration.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, EmailStr
from datetime import timedelta

from app.db.session import get_db
from app.models.user import User
from app.core.deps import get_current_user
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token
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
async def login(credentials: LoginRequest, db: Session = Depends(get_db)):
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

    # Create JWT token
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role
    }
    access_token = create_access_token(data=token_data, expires_delta=access_token_expires)

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
