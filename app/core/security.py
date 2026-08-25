"""
Security utilities for password hashing and JWT token management.
Handles authentication and authorization for the application.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from passlib.context import CryptContext
from jose import JWTError, jwt
from config import settings


# Password hashing configuration using bcrypt
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12
)


def hash_password(password: str) -> str:
    """
    Hash a plain text password using bcrypt.

    Args:
        password (str): Plain text password to hash.

    Returns:
        str: Hashed password.
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain text password against its hashed version.

    Args:
        plain_password (str): Plain text password to verify.
        hashed_password (str): Previously hashed password.

    Returns:
        bool: True if password matches, False otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token with the provided data.

    Args:
        data (Dict[str, Any]): Dictionary of data to encode in token.
        expires_delta (Optional[timedelta]): Custom expiration time. Defaults to 60 minutes.

    Returns:
        str: Encoded JWT token.
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes
        )

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.algorithm
    )

    return encoded_jwt


def verify_token(token: str) -> Dict[str, Any]:
    """
    Verify and decode a JWT token.

    Args:
        token (str): JWT token to verify.

    Returns:
        Dict[str, Any]: Decoded token payload.

    Raises:
        JWTError: If token is invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm]
        )
        return payload
    except JWTError as e:
        raise JWTError(f"Token verification failed: {str(e)}")


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Safely decode a token, returning None if invalid.

    Args:
        token (str): JWT token to decode.

    Returns:
        Optional[Dict[str, Any]]: Decoded token payload or None if invalid.
    """
    try:
        return verify_token(token)
    except JWTError:
        return None
