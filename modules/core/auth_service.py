"""AuthService facade — class-based wrapper over auth_manager functions.

Implements the ``AuthService`` Protocol from ``modules.core.protocols``.
Delegates to existing ``auth_manager`` functions (Strangler Fig pattern)
and to ``UserService`` / ``RoleService`` / ``WorkspaceService`` for
user/role/workspace lookups.

FastAPI dependencies (``require_permission``, ``get_current_user``, etc.)
are **not** part of this facade — they stay in ``auth_manager.py``.
"""

import logging
from typing import Optional

from modules.core.schemas import (
    LoginResult,
    RoleInfo,
    UserInfo,
    WorkspaceInfo,
    WorkspaceMemberInfo,
)


logger = logging.getLogger(__name__)


def _user_dict_to_info(d: dict) -> UserInfo:
    """Convert a dict from UserService/UserRepository to UserInfo TypedDict."""
    return UserInfo(
        id=d["id"],
        username=d["username"],
        role=d.get("role", "user"),
        display_name=d.get("display_name"),
        is_active=d.get("is_active", True),
        workspace_id=d.get("workspace_id", 1),
        created=d.get("created") or d.get("created_at"),
        last_login=d.get("last_login"),
    )


def _role_dict_to_info(d: dict) -> RoleInfo:
    """Convert a dict from RoleService to RoleInfo TypedDict."""
    return RoleInfo(
        id=d["id"],
        name=d["name"],
        display_name=d.get("display_name"),
        description=d.get("description"),
        is_system=d.get("is_system", False),
        permissions=d.get("permissions", {}),
    )


class AuthService:
    """Facade implementing the AuthService Protocol.

    Thin wrapper delegating to ``auth_manager`` functions and domain
    services.  Internal caches (session, permissions, member-role)
    remain in ``auth_manager``; this class doesn't duplicate them.
    """

    # -- Authentication -------------------------------------------------------

    async def authenticate(
        self,
        username: str,
        password: str,
        *,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> LoginResult:
        """Validate credentials, create session, return token + user info.

        Raises ``ValueError`` if credentials are invalid.
        """
        from auth_manager import authenticate_user, create_session

        user = await authenticate_user(username, password)
        if user is None:
            raise ValueError("Invalid credentials")

        login_resp = await create_session(
            username=user.username,
            role=user.role,
            user_id=user.id,
            ip=ip,
            user_agent=user_agent,
            workspace_id=user.workspace_id,
        )

        # Build UserInfo for the response
        user_info = await self.get_user(user.id)
        if user_info is None:
            # Fallback for legacy env-var user (id=0)
            user_info = UserInfo(
                id=user.id,
                username=user.username,
                role=user.role,
                display_name=None,
                is_active=True,
                workspace_id=user.workspace_id,
                created=None,
                last_login=None,
            )

        return LoginResult(
            access_token=login_resp.access_token,
            token_type=login_resp.token_type,
            expires_in=login_resp.expires_in,
            user=user_info,
        )

    async def validate_token(self, token: str) -> Optional[UserInfo]:
        """Decode and validate a JWT.  Returns None if invalid/expired."""
        from auth_manager import _validate_session, decode_token

        payload = decode_token(token)
        if payload is None:
            return None

        user = await _validate_session(payload)
        if user is None:
            return None

        return UserInfo(
            id=user.id,
            username=user.username,
            role=user.role,
            display_name=None,
            is_active=True,
            workspace_id=user.workspace_id,
            created=None,
            last_login=None,
        )

    async def revoke_session(self, jti: str) -> bool:
        """Revoke a single session by its JWT ID."""
        from auth_manager import revoke_session

        return await revoke_session(jti)

    async def revoke_all_sessions(self, user_id: int) -> int:
        """Revoke all active sessions for a user.  Returns count revoked."""
        from auth_manager import revoke_all_user_sessions

        return await revoke_all_user_sessions(user_id)

    # -- Permissions ----------------------------------------------------------

    async def get_permissions(self, user_id: int) -> dict[str, str]:
        """Return the effective permission map for a user."""
        from auth_manager import User as AuthUser
        from auth_manager import get_user_permissions
        from modules.core.service import user_service

        user_data = await user_service.get_by_id(user_id)
        if user_data is None:
            return {}

        # Build a minimal auth_manager.User for the existing function
        auth_user = AuthUser(
            id=user_data["id"],
            username=user_data["username"],
            role=user_data.get("role", "user"),
            workspace_id=user_data.get("workspace_id", 1),
        )
        return await get_user_permissions(auth_user)

    async def has_permission(
        self,
        user_id: int,
        module: str,
        min_level: str = "view",
    ) -> bool:
        """Check whether a user meets the minimum access level for a module."""
        from auth_manager import level_gte

        perms = await self.get_permissions(user_id)
        return level_gte(perms.get(module, ""), min_level)

    # -- User management ------------------------------------------------------

    async def get_user(self, user_id: int) -> Optional[UserInfo]:
        """Look up a user by ID."""
        from modules.core.service import user_service

        data = await user_service.get_by_id(user_id)
        if data is None:
            return None
        return _user_dict_to_info(data)

    async def list_users(
        self,
        *,
        workspace_id: Optional[int] = None,
        include_inactive: bool = False,
    ) -> list[UserInfo]:
        """List users, optionally filtered by workspace."""
        from modules.core.service import user_service

        users = await user_service.list_users(include_inactive=include_inactive)
        result = [_user_dict_to_info(u) for u in users]
        if workspace_id is not None:
            result = [u for u in result if u["workspace_id"] == workspace_id]
        return result

    # -- Roles ----------------------------------------------------------------

    async def get_roles(self) -> list[RoleInfo]:
        """List all RBAC roles with their permission maps."""
        from modules.core.service import role_service

        roles = await role_service.get_all_with_permissions()
        return [_role_dict_to_info(r) for r in roles]

    # -- Workspaces -----------------------------------------------------------

    async def get_workspace(self, workspace_id: int) -> Optional[WorkspaceInfo]:
        """Look up a workspace by ID."""
        from modules.core.service import workspace_service

        data = await workspace_service.get_workspace_info(workspace_id)
        if data is None:
            return None
        return WorkspaceInfo(
            id=data["id"],
            name=data["name"],
            slug=data.get("slug", ""),
            owner_id=data.get("owner_id"),
            created=data.get("created") or data.get("created_at"),
        )

    async def list_members(self, workspace_id: int) -> list[WorkspaceMemberInfo]:
        """List members of a workspace."""
        from modules.core.service import workspace_service

        members = await workspace_service.list_members(workspace_id)
        return [
            WorkspaceMemberInfo(
                user_id=m["user_id"],
                username=m.get("username", ""),
                role_name=m.get("role_name", ""),
                joined_at=m.get("joined_at"),
            )
            for m in members
        ]

    # -- Cache management (not in Protocol) -----------------------------------

    def invalidate_permissions_cache(self, role_name: Optional[str] = None) -> None:
        """Clear permissions cache.  Delegates to auth_manager."""
        from auth_manager import invalidate_permissions_cache

        invalidate_permissions_cache(role_name)

    def invalidate_member_role_cache(self, user_id: int) -> None:
        """Clear member-role cache for a user.  Delegates to auth_manager."""
        from auth_manager import _member_role_cache

        _member_role_cache.invalidate_user(user_id)


auth_service = AuthService()
