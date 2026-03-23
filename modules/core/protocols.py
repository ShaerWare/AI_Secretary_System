"""Target Protocol interfaces for the Core domain (auth & users).

These Protocols describe the *ideal* service contracts.  Currently
auth logic lives in ``auth_manager.py`` (module-level functions);
the Protocols define the target class-based facade.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable


if TYPE_CHECKING:
    from modules.core.schemas import (
        LoginResult,
        RoleInfo,
        UserInfo,
        WorkspaceInfo,
        WorkspaceMemberInfo,
    )


@runtime_checkable
class AuthService(Protocol):
    """Authentication, token management, and RBAC.

    Currently scattered across ``auth_manager.py`` (functions) and
    ``modules/core/service.py`` (UserService, RoleService,
    WorkspaceService).  This Protocol defines the unified target.
    """

    # -- Authentication -------------------------------------------------------

    async def authenticate(
        self,
        username: str,
        password: str,
    ) -> LoginResult:
        """Validate credentials and return an access token + user info."""
        ...

    async def validate_token(self, token: str) -> UserInfo | None:
        """Decode and validate a JWT.  Returns ``None`` if invalid/expired."""
        ...

    async def revoke_session(self, jti: str) -> bool:
        """Revoke a single session by its JWT ID."""
        ...

    async def revoke_all_sessions(self, user_id: int) -> int:
        """Revoke all active sessions for a user.  Returns count revoked."""
        ...

    # -- Permissions ----------------------------------------------------------

    async def get_permissions(self, user_id: int) -> dict[str, str]:
        """Return the effective permission map for a user.

        Keys are module names, values are access levels
        (``"view"`` | ``"edit"`` | ``"manage"``).
        """
        ...

    async def has_permission(
        self,
        user_id: int,
        module: str,
        min_level: str = "view",
    ) -> bool:
        """Check whether a user meets the minimum access level for a module."""
        ...

    # -- User management ------------------------------------------------------

    async def get_user(self, user_id: int) -> UserInfo | None:
        """Look up a user by ID."""
        ...

    async def list_users(
        self,
        *,
        workspace_id: int | None = None,
        include_inactive: bool = False,
    ) -> list[UserInfo]:
        """List users, optionally filtered by workspace."""
        ...

    # -- Roles ----------------------------------------------------------------

    async def get_roles(self) -> list[RoleInfo]:
        """List all RBAC roles with their permission maps."""
        ...

    # -- Workspaces -----------------------------------------------------------

    async def get_workspace(self, workspace_id: int) -> WorkspaceInfo | None:
        """Look up a workspace by ID."""
        ...

    async def list_members(self, workspace_id: int) -> list[WorkspaceMemberInfo]:
        """List members of a workspace."""
        ...
