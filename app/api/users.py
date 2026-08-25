"""
User management API endpoints.
Handles user creation, retrieval, and management with database integration.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, EmailStr
from typing import List

from app.db.session import get_db
from app.models.user import User
from app.core.security import hash_password
from app.core.deps import get_current_user, get_current_admin_user

router = APIRouter(prefix="/api/users", tags=["Users"])


# ============================================================================
# Pydantic Models (Request/Response)
# ============================================================================

class UserCreate(BaseModel):
    """Request model for creating a new user."""

    email: str
    password: str
    full_name: str
    role: str = "topic_monitor"

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "email": "analyst@example.com",
                "password": "secure_password",
                "full_name": "John Analyst",
                "role": "topic_monitor"
            }
        })


class UserResponse(BaseModel):
    """Response model for user information."""

    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    topic_ids: list[int] = []

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    """Request model for updating user information."""

    full_name: str = None
    role: str = None
    is_active: bool = None

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "full_name": "John Updated",
                "role": "super_admin",
                "is_active": True
            }
        })


# ============================================================================
# User Endpoints
# ============================================================================

@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Create a new user (Admin only).

    Args:
        user_data (UserCreate): User creation data.
        db (Session): Database session.
        current_user (User): Current authenticated user (must be admin).

    Returns:
        UserResponse: Created user information.

    Raises:
        HTTPException: If user is not admin, or email already exists.
    """
    # Check if current user is admin
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create users"
        )

    # Check if email already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Validate role
    if user_data.role not in ["super_admin", "topic_admin", "topic_monitor"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be 'super_admin', 'topic_admin', or 'topic_monitor'"
        )

    # Create new user
    new_user = User(
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        full_name=user_data.full_name,
        role=user_data.role,
        is_active=True
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return UserResponse.model_validate(new_user)


@router.get("", response_model=List[UserResponse], status_code=status.HTTP_200_OK)
async def list_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """
    List all users (Admin only).

    Args:
        skip (int): Number of users to skip (pagination).
        limit (int): Maximum number of users to return.
        db (Session): Database session.
        current_user (User): Current authenticated user (must be admin).

    Returns:
        List[UserResponse]: List of users.

    Raises:
        HTTPException: If user is not admin.
    """
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can list users"
        )

    users = db.query(User).offset(skip).limit(limit).all()
    return [UserResponse.model_validate(user) for user in users]


@router.get("/{user_id}", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get user by ID.
    Users can only view their own profile unless they are admins.

    Args:
        user_id (int): ID of user to retrieve.
        db (Session): Database session.
        current_user (User): Current authenticated user.

    Returns:
        UserResponse: User information.

    Raises:
        HTTPException: If user not found or no permission to view.
    """
    # Check permissions: users can only view their own profile, admins can view anyone
    if current_user.id != user_id and current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own profile"
        )

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update user information (Admin only, or self-profile for non-admin fields).

    Args:
        user_id (int): ID of user to update.
        user_update (UserUpdate): Fields to update.
        db (Session): Database session.
        current_user (User): Current authenticated user.

    Returns:
        UserResponse: Updated user information.

    Raises:
        HTTPException: If user not found or no permission to update.
    """
    # Only admin or user updating themselves
    if current_user.id != user_id and current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own profile"
        )

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Non-admin users cannot change their role or is_active status
    if current_user.role != "super_admin":
        if user_update.role is not None or user_update.is_active is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can change role or active status"
            )

    # Update fields
    if user_update.full_name is not None:
        user.full_name = user_update.full_name
    if user_update.role is not None and current_user.role == "super_admin":
        if user_update.role not in ["super_admin", "topic_admin", "topic_monitor"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Role must be 'admin' or 'analyst'"
            )
        user.role = user_update.role
    if user_update.is_active is not None and current_user.role == "super_admin":
        user.is_active = user_update.is_active

    db.add(user)
    db.commit()
    db.refresh(user)

    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Delete a user (Admin only).

    Args:
        user_id (int): ID of user to delete.
        db (Session): Database session.
        current_user (User): Current authenticated user (must be admin).

    Raises:
        HTTPException: If user not found or current user is not admin.
    """
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can delete users"
        )

    # Prevent self-deletion
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    db.delete(user)
    db.commit()
