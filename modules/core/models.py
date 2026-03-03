"""Core models: users, roles, workspaces, system config."""

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base


# ============== User Management ==============


class User(Base):
    """System user with role-based access."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[Optional[str]] = mapped_column(
        String(100), unique=True, index=True, nullable=True
    )
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    salt: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="user")  # guest, user, admin, contact
    display_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", index=True)
    created: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    identities: Mapped[list["UserIdentity"]] = relationship(
        "UserIdentity", back_populates="user", cascade="all, delete-orphan", lazy="noload"
    )

    def to_dict(self, include_sensitive: bool = False) -> dict:
        result: dict[str, Any] = {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "display_name": self.display_name,
            "email": self.email,
            "is_active": self.is_active,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }
        if include_sensitive:
            result["password_hash"] = self.password_hash
            result["salt"] = self.salt
        return result


class UserIdentity(Base):
    """External identity linked to a user (Telegram, WhatsApp, Widget)."""

    __tablename__ = "user_identities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_uid: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="identities")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "provider": self.provider,
            "provider_uid": self.provider_uid,
            "display_name": self.display_name,
            "metadata": json.loads(self.metadata_json) if self.metadata_json else None,
            "created": self.created.isoformat() if self.created else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }


class UserSession(Base):
    """User login session for token revocation and session management."""

    __tablename__ = "user_sessions"
    __table_args__ = (Index("ix_user_sessions_user_revoked", "user_id", "revoked_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    token_jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    workspace_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=True
    )

    user: Mapped["User"] = relationship("User", backref="sessions")

    def to_dict(self) -> dict:
        return {
            "token_jti": self.token_jti,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
        }


# ============== Roles & Permissions ==============


class Role(Base):
    """RBAC role with associated permissions."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )

    permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission", back_populates="role", cascade="all, delete-orphan", lazy="selectin"
    )

    def to_dict(self, include_permissions: bool = True) -> dict:
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "is_system": self.is_system,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_permissions and self.permissions:
            result["permissions"] = {p.module: p.level for p in self.permissions}
        return result


class RolePermission(Base):
    """Single module-level permission entry for a role."""

    __tablename__ = "role_permissions"
    __table_args__ = (Index("ix_role_permissions_role_module", "role_id", "module", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roles.id", ondelete="CASCADE"), index=True
    )
    module: Mapped[str] = mapped_column(String(50))
    level: Mapped[str] = mapped_column(String(10))  # "view", "edit", "manage"

    role: Mapped["Role"] = relationship("Role", back_populates="permissions")


# ============== Workspaces ==============


class Workspace(Base):
    """Multi-tenant workspace container."""

    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    owner_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )

    members: Mapped[list["WorkspaceMember"]] = relationship(
        "WorkspaceMember", back_populates="workspace", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "owner_id": self.owner_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class WorkspaceMember(Base):
    """User membership in a workspace with assigned role."""

    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_user"),
        Index("ix_wm_user_workspace", "user_id", "workspace_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_name: Mapped[str] = mapped_column(String(50), ForeignKey("roles.name"), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )

    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="members")
    user: Mapped["User"] = relationship("User")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "role_name": self.role_name,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
        }


class WorkspaceInvite(Base):
    """Invitation link to join a workspace."""

    __tablename__ = "workspace_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    invite_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    role_name: Mapped[str] = mapped_column(
        String(50), ForeignKey("roles.name"), nullable=False, server_default="viewer"
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    used_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    max_uses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)

    @property
    def is_valid(self) -> bool:
        """Check if invite is still usable (not expired, not exhausted)."""
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return not (self.max_uses is not None and self.used_count >= self.max_uses)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "email": self.email,
            "invite_code": self.invite_code,
            "role_name": self.role_name,
            "created_by": self.created_by,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "used_at": self.used_at.isoformat() if self.used_at else None,
            "used_by": self.used_by,
            "max_uses": self.max_uses,
            "used_count": self.used_count,
            "is_valid": self.is_valid,
        }


class SystemConfig(Base):
    """Key-value system configuration store"""

    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)  # JSON value
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def get_value(self) -> Any:
        """Parse JSON value"""
        try:
            result: Any = json.loads(self.value)
            return result
        except (json.JSONDecodeError, TypeError):
            return self.value

    def set_value(self, value: Any) -> None:
        """Serialize value to JSON"""
        self.value = json.dumps(value, ensure_ascii=False)
