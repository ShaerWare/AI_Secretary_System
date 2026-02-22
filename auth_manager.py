"""
Authentication Manager for Admin Panel

Multi-user JWT-based authentication with DB-backed users and role-based access.
Roles: guest, user, admin.
Session-based token management with in-memory cache and revocation support.
"""

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from utils.password import verify_password as _verify_legacy_password


logger = logging.getLogger(__name__)

# Configuration
JWT_SECRET = os.getenv("ADMIN_JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("ADMIN_JWT_EXPIRATION_HOURS", "24"))

# Legacy env-var credentials (fallback when users table is empty)
_LEGACY_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
_LEGACY_PASSWORD_HASH: str = os.getenv("ADMIN_PASSWORD_HASH", "") or ""
if not _LEGACY_PASSWORD_HASH:
    _LEGACY_PASSWORD_HASH = hashlib.sha256(b"admin").hexdigest()


# ============== Pydantic Models ==============


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = None


class TokenPayload(BaseModel):
    sub: str  # username
    user_id: int  # database user id
    role: str
    exp: int  # expiration timestamp
    iat: int  # issued at timestamp
    jti: str = ""  # JWT ID for session tracking


class User(BaseModel):
    id: int
    username: str
    role: str


# ============== Security ==============

security = HTTPBearer(auto_error=False)


# ============== Session Cache ==============


class SessionCache:
    """In-memory cache mapping JTI → user_id for fast session validation."""

    def __init__(self) -> None:
        self._cache: Dict[str, int] = {}  # jti → user_id

    def get(self, jti: str) -> Optional[int]:
        return self._cache.get(jti)

    def put(self, jti: str, user_id: int) -> None:
        self._cache[jti] = user_id

    def remove(self, jti: str) -> None:
        self._cache.pop(jti, None)

    def remove_all_for_user(self, user_id: int) -> None:
        to_remove = [jti for jti, uid in self._cache.items() if uid == user_id]
        for jti in to_remove:
            del self._cache[jti]

    def size(self) -> int:
        return len(self._cache)


_session_cache = SessionCache()


# ============== Password Helpers ==============
# Centralized in utils/password.py. Legacy env-var fallback uses _verify_legacy_password.


# ============== Token Management ==============


def create_access_token(
    username: str, role: str = "admin", user_id: int = 0
) -> tuple[str, int, str]:
    """Create a JWT access token with a unique JTI.

    Returns:
        tuple: (token, expires_in_seconds, jti)
    """
    now = datetime.utcnow()
    expires = now + timedelta(hours=JWT_EXPIRATION_HOURS)
    expires_in = int((expires - now).total_seconds())
    jti = str(uuid4())

    payload = {
        "sub": username,
        "user_id": user_id,
        "role": role,
        "exp": int(expires.timestamp()),
        "iat": int(now.timestamp()),
        "jti": jti,
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, expires_in, jti


def decode_token(token: str) -> Optional[TokenPayload]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        # Backward compat: old tokens may not have user_id
        if "user_id" not in payload:
            payload["user_id"] = 0
        # Backward compat: old tokens may not have jti
        if "jti" not in payload:
            payload["jti"] = ""
        return TokenPayload(**payload)
    except jwt.ExpiredSignatureError:
        logger.debug("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.debug(f"Invalid token: {e}")
        return None


# ============== Session Management ==============


async def create_session(
    username: str,
    role: str,
    user_id: int,
    ip: Optional[str],
    user_agent: Optional[str],
) -> LoginResponse:
    """Create a new session: generate token, persist to DB, populate cache."""
    from db.integration import async_session_manager

    token, expires_in, jti = create_access_token(username, role, user_id)
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    await async_session_manager.create_session(
        user_id=user_id,
        jti=jti,
        ip_address=ip,
        user_agent=user_agent,
        expires_at=expires_at,
    )
    _session_cache.put(jti, user_id)

    return LoginResponse(access_token=token, token_type="bearer", expires_in=expires_in)


async def revoke_session(jti: str) -> bool:
    """Revoke a single session by JTI."""
    from db.integration import async_session_manager

    _session_cache.remove(jti)
    return await async_session_manager.revoke_by_jti(jti)


async def revoke_all_user_sessions(user_id: int) -> int:
    """Revoke all sessions for a user."""
    from db.integration import async_session_manager

    _session_cache.remove_all_for_user(user_id)
    return await async_session_manager.revoke_all_for_user(user_id)


# ============== Authentication ==============


async def authenticate_user(username: str, password: str) -> Optional[User]:
    """Authenticate user against DB. Falls back to env-var admin if no DB users."""
    try:
        from db.integration import async_user_manager

        user_data = await async_user_manager.authenticate(username, password)
        if user_data:
            return User(
                id=user_data["id"],
                username=user_data["username"],
                role=user_data["role"],
            )

        # If DB auth failed, check if DB has any users at all
        user_count = await async_user_manager.get_user_count()
        if user_count > 0:
            # DB has users, this is a real auth failure
            return None

    except Exception as e:
        logger.warning(f"DB auth failed, trying legacy: {e}")

    # Fallback: legacy env-var admin (when no users in DB or DB unavailable)
    if username == _LEGACY_USERNAME and _verify_legacy_password(password, _LEGACY_PASSWORD_HASH):
        return User(id=0, username=username, role="admin")

    return None


# ============== Session Validation Helpers ==============


async def _validate_session(token_payload: TokenPayload) -> Optional[User]:
    """Validate a decoded token against the session cache/DB.

    Returns User if session is valid, None otherwise.
    """
    jti = token_payload.jti

    # Tokens without jti are pre-session-management tokens — reject
    if not jti:
        return None

    user_id = token_payload.user_id

    # Check in-memory cache first
    cached_uid = _session_cache.get(jti)
    if cached_uid is not None:
        if cached_uid != user_id:
            return None
        return User(id=user_id, username=token_payload.sub, role=token_payload.role)

    # Cache miss — check DB
    from db.integration import async_session_manager

    db_session = await async_session_manager.get_by_jti(jti)
    if db_session is None:
        return None
    if db_session.revoked_at is not None:
        return None
    if db_session.user is None or not db_session.user.is_active:
        return None

    # Valid session — populate cache
    _session_cache.put(jti, user_id)
    return User(id=user_id, username=token_payload.sub, role=token_payload.role)


# ============== FastAPI Dependencies ==============


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    """Dependency to get the current authenticated user."""
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

    user = await _validate_session(token_payload)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session revoked or user deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[User]:
    """Dependency to get the current user if authenticated, None otherwise."""
    if credentials is None:
        return None

    token_payload = decode_token(credentials.credentials)
    if token_payload is None:
        return None

    return await _validate_session(token_payload)


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Dependency to require admin role."""
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def require_not_guest(user: User = Depends(get_current_user)) -> User:
    """Dependency to block guest from write operations. Allows user and admin."""
    if user.role == "guest":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Guest accounts cannot perform this action",
        )
    return user


def verify_ownership(user: User, record_owner_id: Optional[int]) -> None:
    """Raise 404 if user doesn't own the record (admin bypasses)."""
    if user.role == "admin":
        return
    if record_owner_id is not None and record_owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


# ============== Status ==============

AUTH_ENABLED = os.getenv("ADMIN_AUTH_ENABLED", "true").lower() in ("true", "1", "yes")


def get_auth_status() -> Dict:
    """Get current auth configuration status."""
    return {
        "enabled": AUTH_ENABLED,
        "jwt_expiration_hours": JWT_EXPIRATION_HOURS,
        "active_sessions": _session_cache.size(),
    }
