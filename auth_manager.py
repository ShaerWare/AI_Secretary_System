"""
Authentication Manager for Admin Panel

Simple JWT-based authentication with configurable credentials.
"""

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel


logger = logging.getLogger(__name__)

# Configuration
JWT_SECRET = os.getenv("ADMIN_JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("ADMIN_JWT_EXPIRATION_HOURS", "24"))

# Default admin credentials (should be changed in production)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", None)

# If no hash provided, use default password "admin" (for development only)
if not ADMIN_PASSWORD_HASH:
    ADMIN_PASSWORD_HASH = hashlib.sha256(b"admin").hexdigest()
    logger.warning("⚠️ Using default admin password. Set ADMIN_PASSWORD_HASH in production!")


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenPayload(BaseModel):
    sub: str  # username
    role: str
    exp: int  # expiration timestamp
    iat: int  # issued at timestamp


class User(BaseModel):
    username: str
    role: str


security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash a password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash"""
    return hash_password(password) == password_hash


def create_access_token(username: str, role: str = "admin") -> tuple[str, int]:
    """
    Create a JWT access token.

    Returns:
        tuple: (token, expires_in_seconds)
    """
    now = datetime.utcnow()
    expires = now + timedelta(hours=JWT_EXPIRATION_HOURS)
    expires_in = int((expires - now).total_seconds())

    payload = {
        "sub": username,
        "role": role,
        "exp": int(expires.timestamp()),
        "iat": int(now.timestamp()),
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, expires_in


def decode_token(token: str) -> Optional[TokenPayload]:
    """
    Decode and validate a JWT token.

    Returns:
        TokenPayload if valid, None if invalid
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return TokenPayload(**payload)
    except jwt.ExpiredSignatureError:
        logger.debug("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.debug(f"Invalid token: {e}")
        return None


def authenticate_user(username: str, password: str) -> Optional[User]:
    """
    Authenticate a user with username and password.

    Currently supports single admin user. Can be extended for multiple users.

    Returns:
        User if authenticated, None otherwise
    """
    if username == ADMIN_USERNAME and verify_password(password, ADMIN_PASSWORD_HASH):
        return User(username=username, role="admin")

    return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[User]:
    """
    Dependency to get the current authenticated user.

    Returns:
        User if authenticated, raises HTTPException otherwise
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_payload = decode_token(credentials.credentials)
    if token_payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return User(username=token_payload.sub, role=token_payload.role)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[User]:
    """
    Dependency to get the current user if authenticated, None otherwise.

    Use this for endpoints that work both with and without authentication.
    """
    if credentials is None:
        return None

    token_payload = decode_token(credentials.credentials)
    if token_payload is None:
        return None

    return User(username=token_payload.sub, role=token_payload.role)


def require_admin(user: User = Depends(get_current_user)) -> User:
    """
    Dependency to require admin role.
    """
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


# Convenience function to check if auth is enabled
AUTH_ENABLED = os.getenv("ADMIN_AUTH_ENABLED", "true").lower() in ("true", "1", "yes")


def get_auth_status() -> Dict:
    """Get current auth configuration status"""
    return {
        "enabled": AUTH_ENABLED,
        "jwt_expiration_hours": JWT_EXPIRATION_HOURS,
        "username": ADMIN_USERNAME,
    }
