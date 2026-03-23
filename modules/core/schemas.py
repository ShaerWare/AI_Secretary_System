"""Ideal data shapes for the Core domain (auth, users, workspaces).

These TypedDicts describe the *target* API contract for
authentication, user management, and RBAC.
"""

from __future__ import annotations

from typing import TypedDict


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class UserInfo(TypedDict):
    """Public user profile — no secrets."""

    id: int
    username: str
    role: str  # legacy role
    display_name: str | None
    is_active: bool
    workspace_id: int
    created: str | None
    last_login: str | None


# ---------------------------------------------------------------------------
# Auth tokens
# ---------------------------------------------------------------------------


class TokenInfo(TypedDict):
    """Decoded JWT payload."""

    sub: str  # username
    user_id: int
    role: str
    workspace_id: int
    exp: int
    iat: int
    jti: str


class LoginResult(TypedDict):
    """Returned by AuthService.authenticate()."""

    access_token: str
    token_type: str  # "bearer"
    expires_in: int  # seconds
    user: UserInfo


# ---------------------------------------------------------------------------
# Permissions / RBAC
# ---------------------------------------------------------------------------


class PermissionMap(TypedDict, total=False):
    """Module → access level mapping.

    Keys are module names (``"channels"``, ``"knowledge"``, …).
    Values are levels: ``"view"`` | ``"edit"`` | ``"manage"``.
    """

    channels: str
    knowledge: str
    llm: str
    tts: str
    monitoring: str
    chat: str
    crm: str
    settings: str
    users: str
    backup: str


class RoleInfo(TypedDict):
    """Read-only view of an RBAC role."""

    id: int
    name: str
    display_name: str | None
    description: str | None
    is_system: bool
    permissions: dict[str, str]  # module → level


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------


class WorkspaceInfo(TypedDict):
    """Read-only view of a workspace."""

    id: int
    name: str
    slug: str
    owner_id: int | None
    created: str | None


class WorkspaceMemberInfo(TypedDict):
    """Read-only view of a workspace membership."""

    user_id: int
    username: str
    role_name: str
    joined_at: str | None
