"""Core services."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from db.database import AsyncSessionLocal, close_db, get_db_status, init_db
from db.redis_client import close_redis, get_redis_status, init_redis
from db.repositories import (
    ConfigRepository,
    RoleRepository,
    UserIdentityRepository,
    UserRepository,
    UserSessionRepository,
    WorkspaceRepository,
)
from db.retry import retry_on_busy


logger = logging.getLogger(__name__)


class DatabaseService:
    """Singleton manager for database operations.
    Provides async context managers for repository access.
    """

    _instance = None
    _initialized = False

    def __new__(cls) -> "DatabaseService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(self) -> None:
        """Initialize database and Redis connections."""
        if self._initialized:
            return

        logger.info("\ud83d\uddc4\ufe0f Initializing database...")
        await init_db()

        logger.info("\ud83d\udd34 Initializing Redis...")
        redis_ok = await init_redis()
        if not redis_ok:
            logger.warning("\u26a0\ufe0f Redis not available, caching disabled")

        self._initialized = True
        logger.info("\u2705 Database ready")

    async def shutdown(self) -> None:
        """Close all connections."""
        await close_db()
        await close_redis()
        self._initialized = False
        logger.info("\ud83d\uddc4\ufe0f Database connections closed")

    async def get_status(self) -> dict:
        """Get database and Redis status for health checks."""
        db_status = await get_db_status()
        redis_status = await get_redis_status()
        return {
            "database": {
                "sqlite": db_status,
                "redis": redis_status,
            }
        }


class UserService:
    """Async manager for user authentication and CRUD."""

    async def authenticate(self, username: str, password: str) -> Optional[dict]:
        """Authenticate user. Returns user dict or None."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            return await repo.authenticate(username, password)

    async def get_by_username(self, username: str) -> Optional[dict]:
        """Get user by username."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            user = await repo.get_by_username(username)
            return user.to_dict() if user else None

    async def get_by_id(self, user_id: int) -> Optional[dict]:
        """Get user by ID."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            user = await repo.get_by_id(user_id)
            return user.to_dict() if user else None

    async def create_user(
        self,
        username: str,
        password: str,
        role: str = "user",
        display_name: Optional[str] = None,
    ) -> dict:
        """Create a new user."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            result = await repo.create_user(username, password, role, display_name)
            await session.commit()
            return result

    async def update_password(self, user_id: int, new_password: str) -> bool:
        """Update user password. Revokes all existing sessions."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            result = await repo.update_password(user_id, new_password)
            await session.commit()
        if result:
            await self._revoke_user_sessions(user_id)
        return result

    async def update_profile(
        self, user_id: int, display_name: Optional[str] = None
    ) -> Optional[dict]:
        """Update user profile."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            result = await repo.update_profile(user_id, display_name)
            await session.commit()
            return result

    async def set_role(self, user_id: int, role: str) -> bool:
        """Change user role. Revokes all existing sessions."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            result = await repo.set_role(user_id, role)
            await session.commit()
        if result:
            await self._revoke_user_sessions(user_id)
        return result

    async def set_active(self, user_id: int, active: bool) -> bool:
        """Enable or disable user. Revokes sessions on deactivation."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            result = await repo.set_active(user_id, active)
            await session.commit()
        if result and not active:
            await self._revoke_user_sessions(user_id)
        return result

    async def _revoke_user_sessions(self, user_id: int) -> None:
        """Revoke all sessions and clear cache for a user."""
        from auth_manager import revoke_all_user_sessions

        try:
            await revoke_all_user_sessions(user_id)
        except Exception as e:
            logger.warning(f"Failed to revoke sessions for user {user_id}: {e}")

    async def list_users(self, include_inactive: bool = False) -> List[dict]:
        """List all users."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            return await repo.list_users(include_inactive)

    async def delete_user(self, user_id: int) -> bool:
        """Delete user."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            result = await repo.delete_user(user_id)
            await session.commit()
            return result

    async def get_user_count(self) -> int:
        """Get active user count."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            return await repo.get_user_count()


class UserSessionService:
    """Async manager for user session tracking and revocation."""

    @retry_on_busy()
    async def create_session(
        self,
        user_id: int,
        jti: str,
        ip_address: Optional[str],
        user_agent: Optional[str],
        expires_at: "datetime",
        workspace_id: Optional[int] = None,
    ) -> dict:
        """Create a new session record."""
        async with AsyncSessionLocal() as session:
            repo = UserSessionRepository(session)
            result = await repo.create_session(
                user_id,
                jti,
                ip_address,
                user_agent,
                expires_at,
                workspace_id=workspace_id,
            )
            await session.commit()
            return result

    async def get_by_jti(self, jti: str):
        """Get session by JTI with user join."""
        async with AsyncSessionLocal() as session:
            repo = UserSessionRepository(session)
            return await repo.get_by_jti(jti)

    async def get_active_for_user(self, user_id: int) -> List[dict]:
        """Get active sessions for a user."""
        async with AsyncSessionLocal() as session:
            repo = UserSessionRepository(session)
            return await repo.get_active_for_user(user_id)

    @retry_on_busy()
    async def revoke_by_jti(self, jti: str) -> bool:
        """Revoke a single session."""
        async with AsyncSessionLocal() as session:
            repo = UserSessionRepository(session)
            result = await repo.revoke_by_jti(jti)
            await session.commit()
            return result

    async def revoke_all_for_user(self, user_id: int) -> int:
        """Revoke all sessions for a user."""
        async with AsyncSessionLocal() as session:
            repo = UserSessionRepository(session)
            result = await repo.revoke_all_for_user(user_id)
            await session.commit()
            return result

    @retry_on_busy()
    async def cleanup_expired(self, days: int = 7) -> int:
        """Delete old expired sessions."""
        async with AsyncSessionLocal() as session:
            repo = UserSessionRepository(session)
            result = await repo.cleanup_expired(days)
            await session.commit()
            return result


class RoleService:
    """Async role manager for RBAC."""

    async def get_by_name(self, name: str) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = RoleRepository(session)
            role = await repo.get_by_name(name)
            return role.to_dict() if role else None

    async def get_with_permissions(self, role_id: int) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = RoleRepository(session)
            role = await repo.get_with_permissions(role_id)
            return role.to_dict() if role else None

    async def get_all_with_permissions(self) -> List[dict]:
        async with AsyncSessionLocal() as session:
            repo = RoleRepository(session)
            roles = await repo.get_all_with_permissions()
            return [r.to_dict() for r in roles]

    async def create_role(
        self,
        name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        is_system: bool = False,
        permissions: Optional[Dict[str, str]] = None,
    ) -> dict:
        async with AsyncSessionLocal() as session:
            repo = RoleRepository(session)
            role = await repo.create_role(name, display_name, description, is_system, permissions)
            await session.commit()
            return role.to_dict()

    async def update_role(
        self,
        role_id: int,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        permissions: Optional[Dict[str, str]] = None,
    ) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = RoleRepository(session)
            role = await repo.update_role(role_id, display_name, description, permissions)
            await session.commit()
            return role.to_dict() if role else None

    async def delete_role(self, role_id: int) -> bool:
        async with AsyncSessionLocal() as session:
            repo = RoleRepository(session)
            result = await repo.delete_role(role_id)
            await session.commit()
            return result

    async def count(self) -> int:
        async with AsyncSessionLocal() as session:
            repo = RoleRepository(session)
            return await repo.count()


class WorkspaceService:
    """Async manager for workspace operations."""

    async def get_member_role_name(self, user_id: int, workspace_id: int) -> Optional[str]:
        """Get role_name for (user_id, workspace_id) from workspace_members."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            return await repo.get_member_role_name(user_id, workspace_id)

    async def ensure_membership(self, workspace_id: int, user_id: int, role_name: str) -> None:
        """Insert or update workspace membership (idempotent)."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            await repo.ensure_membership(workspace_id, user_id, role_name)
            await session.commit()

    async def get_default_workspace(self) -> Optional[dict]:
        """Get workspace with id=1."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            return await repo.get_default_workspace()

    async def create_default(self, name: str = "Default", slug: str = "default") -> dict:
        """Create the default workspace."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            result = await repo.create_default(name, slug)
            await session.commit()
            return result

    # ============== Members Management ==============

    async def get_workspace_info(self, workspace_id: int) -> Optional[dict]:
        """Get workspace by ID with member count."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            return await repo.get_workspace_info(workspace_id)

    async def list_members(self, workspace_id: int) -> List[dict]:
        """List all members of a workspace with user details."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            return await repo.list_members(workspace_id)

    async def update_member_role(
        self, workspace_id: int, user_id: int, role_name: str
    ) -> Optional[dict]:
        """Change a member's role."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            result = await repo.update_member_role(workspace_id, user_id, role_name)
            await session.commit()
            return result

    async def remove_member(self, workspace_id: int, user_id: int) -> bool:
        """Remove a member from workspace."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            result = await repo.remove_member(workspace_id, user_id)
            await session.commit()
            return result

    async def get_workspace_owner_id(self, workspace_id: int) -> Optional[int]:
        """Get the owner_id for a workspace."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            return await repo.get_workspace_owner_id(workspace_id)

    # ============== Invites ==============

    async def create_invite(
        self,
        workspace_id: int,
        role_name: str,
        created_by: int,
        email: Optional[str] = None,
        max_uses: Optional[int] = None,
        expires_hours: Optional[int] = None,
    ) -> dict:
        """Create an invite link."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            result = await repo.create_invite(
                workspace_id, role_name, created_by, email, max_uses, expires_hours
            )
            await session.commit()
            return result

    async def list_invites(self, workspace_id: int) -> List[dict]:
        """List all invites for a workspace."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            return await repo.list_invites(workspace_id)

    async def delete_invite(self, workspace_id: int, invite_id: int) -> bool:
        """Delete an invite."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            result = await repo.delete_invite(workspace_id, invite_id)
            await session.commit()
            return result

    async def get_invite_info(self, invite_code: str) -> Optional[dict]:
        """Get public invite info by code (workspace name, role, expiry)."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            invite = await repo.get_invite_by_code(invite_code)
            if not invite or not invite.is_valid:
                return None
            ws = await repo.get_by_id(invite.workspace_id)
            return {
                "workspace_name": ws.name if ws else "Unknown",
                "role_name": invite.role_name,
                "expires_at": invite.expires_at.isoformat() if invite.expires_at else None,
            }

    async def accept_invite(
        self,
        invite_code: str,
        username: str,
        password: str,
        display_name: Optional[str] = None,
    ) -> Optional[dict]:
        """Accept an invite: create user + membership. Returns user dict or None."""
        # Lazy imports to avoid circular dependency
        from db.models import User, WorkspaceMember
        from utils.password import hash_password

        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            invite = await repo.get_invite_by_code(invite_code)
            if not invite or not invite.is_valid:
                return None
            # Create user
            pw_hash, salt = hash_password(password)
            user = User(
                username=username,
                password_hash=pw_hash,
                salt=salt,
                role="user",
                display_name=display_name or username,
                is_active=True,
            )
            session.add(user)
            await session.flush()  # get user.id
            # Create membership
            session.add(
                WorkspaceMember(
                    workspace_id=invite.workspace_id,
                    user_id=user.id,
                    role_name=invite.role_name,
                )
            )
            # Record usage
            invite.used_count += 1
            invite.used_at = datetime.utcnow()
            invite.used_by = user.id
            await session.commit()
            await session.refresh(user)
            return {
                "user": user.to_dict(),
                "workspace_id": invite.workspace_id,
                "role_name": invite.role_name,
            }


class ConfigService:
    """Async config manager using database."""

    async def get(self, key: str, default: Any = None) -> Any:
        """Get config value."""
        async with AsyncSessionLocal() as session:
            repo = ConfigRepository(session)
            return await repo.get_config(key, default)

    async def set(self, key: str, value: Any) -> bool:
        """Set config value."""
        async with AsyncSessionLocal() as session:
            repo = ConfigRepository(session)
            result = await repo.set_config(key, value)
            await session.commit()
            return result

    async def get_telegram(self) -> dict:
        """Get Telegram config."""
        async with AsyncSessionLocal() as session:
            repo = ConfigRepository(session)
            return await repo.get_telegram_config()

    async def set_telegram(self, config: dict) -> bool:
        """Set Telegram config."""
        async with AsyncSessionLocal() as session:
            repo = ConfigRepository(session)
            result = await repo.set_telegram_config(config)
            await session.commit()
            return result

    async def get_widget(self) -> dict:
        """Get widget config."""
        async with AsyncSessionLocal() as session:
            repo = ConfigRepository(session)
            return await repo.get_widget_config()

    async def set_widget(self, config: dict) -> bool:
        """Set widget config."""
        async with AsyncSessionLocal() as session:
            repo = ConfigRepository(session)
            result = await repo.set_widget_config(config)
            await session.commit()
            return result


class UserIdentityService:
    """Async manager for external user identities (Telegram, WhatsApp, Widget)."""

    async def find_or_create(
        self,
        provider: str,
        provider_uid: str,
        display_name: Optional[str] = None,
        metadata_dict: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """Find existing identity or create contact user + identity."""
        async with AsyncSessionLocal() as session:
            repo = UserIdentityRepository(session)
            result = await repo.find_or_create(provider, provider_uid, display_name, metadata_dict)
            await session.commit()
            return result

    async def get_identities_for_user(self, user_id: int) -> List[dict]:
        """Get all identities linked to a user."""
        async with AsyncSessionLocal() as session:
            repo = UserIdentityRepository(session)
            return await repo.get_identities_for_user(user_id)

    async def link_identity(
        self,
        user_id: int,
        provider: str,
        provider_uid: str,
        display_name: Optional[str] = None,
        metadata_dict: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """Link an external identity to an existing user."""
        async with AsyncSessionLocal() as session:
            repo = UserIdentityRepository(session)
            result = await repo.link_identity(
                user_id, provider, provider_uid, display_name, metadata_dict
            )
            await session.commit()
            return result

    async def update_last_seen(self, provider: str, provider_uid: str) -> bool:
        """Touch the last_seen timestamp for an identity."""
        async with AsyncSessionLocal() as session:
            repo = UserIdentityRepository(session)
            result = await repo.update_last_seen(provider, provider_uid)
            await session.commit()
            return result


# Singletons
database_service = DatabaseService()
user_service = UserService()
user_session_service = UserSessionService()
role_service = RoleService()
workspace_service = WorkspaceService()
config_service = ConfigService()
user_identity_service = UserIdentityService()
