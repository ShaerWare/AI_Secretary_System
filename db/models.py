"""
SQLAlchemy ORM models for AI Secretary System.

Tables:
- users: System users with roles (guest, user, admin)
- chat_sessions: Chat session metadata
- chat_messages: Individual chat messages
- faq_entries: FAQ question-answer pairs
- tts_presets: Custom TTS voice presets
- system_config: Key-value system configuration
- telegram_sessions: Telegram user sessions (per bot instance)
- audit_log: System audit trail
- bot_instances: Telegram bot instances with individual configs
- widget_instances: Website widget instances with individual configs
- whatsapp_instances: WhatsApp bot instances with individual configs
- cloud_llm_providers: Cloud LLM provider configurations (Gemini, Kimi, OpenAI, etc.)
- knowledge_collections: Knowledge base collections (document containers)
- knowledge_documents: Knowledge base document tracking (wiki-pages/)

amoCRM tables:
- amocrm_config: OAuth configuration and sync settings (singleton)
- amocrm_sync_log: Sync event history

Sales bot tables:
- bot_agent_prompts: LLM prompts per bot/context (segment, funnel stage)
- bot_quiz_questions: Segmentation quiz questions with answer options
- bot_segments: User segment definitions and routing rules
- bot_user_profiles: User FSM state, segment, quiz answers
- bot_followup_rules: Automated follow-up trigger rules
- bot_followup_queue: Pending follow-up messages queue
- bot_events: Funnel event tracking / analytics
- bot_testimonials: Social proof testimonials
- bot_hardware_specs: GPU model capabilities for hardware audit
- bot_ab_tests: A/B test definitions
- bot_discovery_responses: Custom path discovery flow answers
- bot_subscribers: News/updates subscription list
- bot_github_configs: GitHub webhook + PR comment config per bot
"""

import enum
import json
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models"""

    pass


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


# ============== Chat ==============


class ChatSession(Base):
    """Chat session with optional system prompt"""

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), default="Новый чат")
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Owner (multi-user isolation, NULL = admin/legacy)
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )

    # Pinned chat (stays at top of list)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    # Context files (JSON: [{"name": "file.txt", "content": "..."}])
    context_files: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Source tracking (admin, telegram, widget)
    source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # RAG configuration (NULL = inherit from source instance)
    rag_mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    knowledge_collection_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("knowledge_collections.id"), nullable=True
    )
    knowledge_collection_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # amoCRM lead tracking (widget → CRM)
    amocrm_lead_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    amocrm_contact_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    visitor_metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    # Relationships
    messages: Mapped[List["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created",
    )

    def to_dict(self, include_messages: bool = True) -> dict:
        result: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "system_prompt": self.system_prompt,
            "pinned": self.pinned,
            "context_files": json.loads(self.context_files) if self.context_files else [],
            "source": self.source,
            "source_id": self.source_id,
            "owner_id": self.owner_id,
            "rag_mode": self.rag_mode,
            "knowledge_collection_id": self.knowledge_collection_id,
            "knowledge_collection_ids": json.loads(self.knowledge_collection_ids)
            if self.knowledge_collection_ids
            else None,
            "amocrm_lead_id": self.amocrm_lead_id,
            "amocrm_contact_id": self.amocrm_contact_id,
            "visitor_metadata": json.loads(self.visitor_metadata)
            if self.visitor_metadata
            else None,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }
        if include_messages:
            result["messages"] = [m.to_dict() for m in self.messages if m.is_active]
        return result

    def to_summary(self) -> dict:
        """Return summary for list view"""
        messages = [m for m in (self.messages or []) if m.is_active]
        last_msg = messages[-1].content[:100] if messages else None
        return {
            "id": self.id,
            "title": self.title,
            "pinned": self.pinned,
            "message_count": len(messages),
            "last_message": last_msg,
            "source": self.source,
            "source_id": self.source_id,
            "owner_id": self.owner_id,
            "rag_mode": self.rag_mode,
            "knowledge_collection_id": self.knowledge_collection_id,
            "knowledge_collection_ids": json.loads(self.knowledge_collection_ids)
            if self.knowledge_collection_ids
            else None,
            "amocrm_lead_id": self.amocrm_lead_id,
            "amocrm_contact_id": self.amocrm_contact_id,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class ChatMessage(Base):
    """Individual message in a chat session"""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20))  # user, assistant, system
    content: Mapped[str] = mapped_column(Text)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Branching fields
    parent_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("chat_messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")
    children: Mapped[List["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="parent",
        foreign_keys=[parent_id],
    )
    parent: Mapped[Optional["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="children",
        foreign_keys=[parent_id],
        remote_side=[id],
    )

    __table_args__ = (Index("ix_chat_messages_session_created", "session_id", "created"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "edited": self.edited,
            "timestamp": self.created.isoformat() if self.created else None,
            "parent_id": self.parent_id,
            "is_active": self.is_active,
        }


class ChatSessionShare(Base):
    """Sharing access for chat sessions between users."""

    __tablename__ = "chat_session_shares"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    permission: Mapped[str] = mapped_column(String(10), default="read")  # "read" or "write"
    shared_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    shared_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    branch_message_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        Index("ix_chat_session_shares_session_user", "session_id", "user_id", unique=True),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "permission": self.permission,
            "shared_by": self.shared_by,
            "shared_at": self.shared_at.isoformat() if self.shared_at else None,
            "branch_message_id": self.branch_message_id,
        }


class ResourceShare(Base):
    """Sharing access for bot/widget/whatsapp instances between users."""

    __tablename__ = "resource_shares"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_type: Mapped[str] = mapped_column(
        String(30), index=True
    )  # "bot_instance", "widget_instance", "whatsapp_instance"
    resource_id: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    permission: Mapped[str] = mapped_column(String(10), default="view")  # "view" or "edit"
    shared_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    shared_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index(
            "ix_resource_shares_type_resource_user",
            "resource_type",
            "resource_id",
            "user_id",
            unique=True,
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "user_id": self.user_id,
            "permission": self.permission,
            "shared_by": self.shared_by,
            "shared_at": self.shared_at.isoformat() if self.shared_at else None,
        }


class FAQEntry(Base):
    """FAQ question-answer pair with fuzzy matching support"""

    __tablename__ = "faq_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    answer: Mapped[str] = mapped_column(Text)
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "question": self.question,
            "answer": self.answer,
            "keywords": json.loads(self.keywords) if self.keywords else [],
            "enabled": self.enabled,
            "hit_count": self.hit_count,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }

    @classmethod
    def from_legacy(cls, question: str, answer: str) -> "FAQEntry":
        """Create from legacy JSON format (question: answer)"""
        return cls(question=question.lower(), answer=answer, enabled=True)


class TTSPreset(Base):
    """Custom TTS voice preset with parameters"""

    __tablename__ = "tts_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    params: Mapped[str] = mapped_column(Text)  # JSON object with TTS parameters
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "params": json.loads(self.params) if self.params else {},
            "builtin": self.builtin,
        }

    def get_params(self) -> dict:
        result: dict = json.loads(self.params) if self.params else {}
        return result

    def set_params(self, params: dict) -> None:
        self.params = json.dumps(params, ensure_ascii=False)


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


class TelegramSession(Base):
    """Telegram user session mapping (per bot instance)"""

    __tablename__ = "telegram_sessions"

    # Composite primary key: bot_id + user_id
    bot_id: Mapped[str] = mapped_column(String(50), primary_key=True, default="default")
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_session_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
    )
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (Index("ix_telegram_sessions_bot_user", "bot_id", "user_id"),)

    def to_dict(self) -> dict:
        return {
            "bot_id": self.bot_id,
            "user_id": self.user_id,
            "chat_session_id": self.chat_session_id,
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class AuditLog(Base):
    """System audit trail for compliance"""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    action: Mapped[str] = mapped_column(
        String(50), index=True
    )  # create, update, delete, login, etc.
    resource: Mapped[str] = mapped_column(String(100))  # chat, faq, tts, config, etc.
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    user_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    __table_args__ = (Index("ix_audit_log_timestamp_action", "timestamp", "action"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "action": self.action,
            "resource": self.resource,
            "resource_id": self.resource_id,
            "user_id": self.user_id,
            "user_ip": self.user_ip,
            "details": json.loads(self.details) if self.details else None,
        }


class BotInstance(Base):
    """Telegram bot instance with individual configuration"""

    __tablename__ = "bot_instances"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # slug like "sales-bot"
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    auto_start: Mapped[bool] = mapped_column(Boolean, default=False)  # Auto-start on app launch
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )

    # Telegram configuration
    bot_token: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    api_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Tunnel URL for API
    allowed_users: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    admin_users: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    welcome_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unauthorized_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    typing_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Action buttons configuration (JSON array)
    action_buttons: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # AI configuration
    llm_backend: Mapped[str] = mapped_column(String(20), default="vllm")  # vllm or gemini
    llm_persona: Mapped[str] = mapped_column(String(50), default="anna")
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_params: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON: temperature, etc.

    # TTS configuration
    tts_engine: Mapped[str] = mapped_column(String(20), default="xtts")  # xtts, piper, openvoice
    tts_voice: Mapped[str] = mapped_column(String(50), default="anna")
    tts_preset: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Payment configuration
    payment_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    yookassa_provider_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    stars_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_products: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    payment_success_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # RAG configuration
    rag_mode: Mapped[str] = mapped_column(String(20), default="all", server_default="all")
    knowledge_collection_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("knowledge_collections.id"), nullable=True
    )
    knowledge_collection_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Sales funnel
    sales_funnel_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    # Rate limiting
    rate_limit_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rate_limit_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # YooMoney OAuth2 configuration
    yoomoney_client_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    yoomoney_client_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    yoomoney_access_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    yoomoney_wallet_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    yoomoney_redirect_uri: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Timestamps
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def get_allowed_users(self) -> List[int]:
        if not self.allowed_users:
            return []
        try:
            result: List[int] = json.loads(self.allowed_users)
            return result
        except (json.JSONDecodeError, TypeError):
            return []

    def set_allowed_users(self, users: List[int]) -> None:
        self.allowed_users = json.dumps(users)

    def get_admin_users(self) -> List[int]:
        if not self.admin_users:
            return []
        try:
            result: List[int] = json.loads(self.admin_users)
            return result
        except (json.JSONDecodeError, TypeError):
            return []

    def set_admin_users(self, users: List[int]) -> None:
        self.admin_users = json.dumps(users)

    def get_llm_params(self) -> dict:
        if not self.llm_params:
            return {}
        try:
            result: dict = json.loads(self.llm_params)
            return result
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_llm_params(self, params: dict) -> None:
        self.llm_params = json.dumps(params, ensure_ascii=False)

    def get_action_buttons(self) -> List[dict]:
        """Get action buttons configuration."""
        if not self.action_buttons:
            return []
        try:
            result: List[dict] = json.loads(self.action_buttons)
            return result
        except (json.JSONDecodeError, TypeError):
            return []

    def set_action_buttons(self, buttons: List[dict]) -> None:
        """Set action buttons configuration."""
        self.action_buttons = json.dumps(buttons, ensure_ascii=False)

    def get_payment_products(self) -> List[dict]:
        """Get payment products configuration."""
        if not self.payment_products:
            return []
        try:
            result: List[dict] = json.loads(self.payment_products)
            return result
        except (json.JSONDecodeError, TypeError):
            return []

    def set_payment_products(self, products: List[dict]) -> None:
        """Set payment products configuration."""
        self.payment_products = json.dumps(products, ensure_ascii=False)

    def to_dict(self, include_token: bool = False) -> dict:
        result = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "auto_start": self.auto_start,
            # Telegram
            "bot_token_masked": "***" + self.bot_token[-4:]
            if self.bot_token and len(self.bot_token) > 4
            else "",
            "api_url": self.api_url,
            "allowed_users": self.get_allowed_users(),
            "admin_users": self.get_admin_users(),
            "welcome_message": self.welcome_message,
            "unauthorized_message": self.unauthorized_message,
            "error_message": self.error_message,
            "typing_enabled": self.typing_enabled,
            # AI
            "llm_backend": self.llm_backend,
            "llm_persona": self.llm_persona,
            "system_prompt": self.system_prompt,
            "llm_params": self.get_llm_params(),
            # TTS
            "tts_engine": self.tts_engine,
            "tts_voice": self.tts_voice,
            "tts_preset": self.tts_preset,
            # Action buttons
            "action_buttons": self.get_action_buttons(),
            # Payment
            "payment_enabled": self.payment_enabled,
            "yookassa_provider_token_masked": "***" + self.yookassa_provider_token[-4:]
            if self.yookassa_provider_token and len(self.yookassa_provider_token) > 4
            else "",
            "stars_enabled": self.stars_enabled,
            "payment_products": self.get_payment_products(),
            "payment_success_message": self.payment_success_message,
            # RAG
            "rag_mode": self.rag_mode,
            "knowledge_collection_id": self.knowledge_collection_id,
            "knowledge_collection_ids": json.loads(self.knowledge_collection_ids)
            if self.knowledge_collection_ids
            else None,
            # Sales funnel
            "sales_funnel_enabled": self.sales_funnel_enabled,
            # Rate limiting
            "rate_limit_count": self.rate_limit_count,
            "rate_limit_hours": self.rate_limit_hours,
            # YooMoney
            "yoomoney_client_id": self.yoomoney_client_id,
            "yoomoney_configured": bool(self.yoomoney_access_token),
            "yoomoney_wallet_id": self.yoomoney_wallet_id,
            # Timestamps
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }
        if include_token and self.bot_token:
            result["bot_token"] = self.bot_token
        return result


class WidgetInstance(Base):
    """Website widget instance with individual configuration"""

    __tablename__ = "widget_instances"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # slug like "support-widget"
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )

    # Appearance
    title: Mapped[str] = mapped_column(String(100), default="AI Ассистент")
    greeting: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    placeholder: Mapped[str] = mapped_column(String(200), default="Введите сообщение...")
    placeholder_color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    placeholder_font: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    primary_color: Mapped[str] = mapped_column(String(20), default="#c2410c")
    button_icon: Mapped[str] = mapped_column(String(20), default="chat")
    position: Mapped[str] = mapped_column(String(20), default="right")  # left or right
    button_size: Mapped[int] = mapped_column(Integer, default=60)
    button_offset_bottom: Mapped[int] = mapped_column(Integer, default=20)
    button_offset_side: Mapped[int] = mapped_column(Integer, default=20)

    # Access control
    allowed_domains: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    tunnel_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # AI configuration
    llm_backend: Mapped[str] = mapped_column(String(20), default="vllm")
    llm_persona: Mapped[str] = mapped_column(String(50), default="anna")
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_params: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    # TTS configuration
    tts_engine: Mapped[str] = mapped_column(String(20), default="xtts")
    tts_voice: Mapped[str] = mapped_column(String(50), default="anna")
    tts_preset: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # RAG configuration
    rag_mode: Mapped[str] = mapped_column(String(20), default="all", server_default="all")
    knowledge_collection_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("knowledge_collections.id"), nullable=True
    )
    knowledge_collection_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Rate limiting
    rate_limit_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rate_limit_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Timestamps
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def get_allowed_domains(self) -> List[str]:
        if not self.allowed_domains:
            return []
        try:
            result: List[str] = json.loads(self.allowed_domains)
            return result
        except (json.JSONDecodeError, TypeError):
            return []

    def set_allowed_domains(self, domains: List[str]) -> None:
        self.allowed_domains = json.dumps(domains)

    def get_llm_params(self) -> dict:
        if not self.llm_params:
            return {}
        try:
            result: dict = json.loads(self.llm_params)
            return result
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_llm_params(self, params: dict) -> None:
        self.llm_params = json.dumps(params, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            # Appearance
            "title": self.title,
            "greeting": self.greeting,
            "placeholder": self.placeholder,
            "placeholder_color": self.placeholder_color,
            "placeholder_font": self.placeholder_font,
            "primary_color": self.primary_color,
            "button_icon": self.button_icon,
            "position": self.position,
            # Access
            "allowed_domains": self.get_allowed_domains(),
            "tunnel_url": self.tunnel_url,
            # AI
            "llm_backend": self.llm_backend,
            "llm_persona": self.llm_persona,
            "system_prompt": self.system_prompt,
            "llm_params": self.get_llm_params(),
            # TTS
            "tts_engine": self.tts_engine,
            "tts_voice": self.tts_voice,
            "tts_preset": self.tts_preset,
            # RAG
            "rag_mode": self.rag_mode,
            "knowledge_collection_id": self.knowledge_collection_id,
            "knowledge_collection_ids": json.loads(self.knowledge_collection_ids)
            if self.knowledge_collection_ids
            else None,
            # Rate limiting
            "rate_limit_count": self.rate_limit_count,
            "rate_limit_hours": self.rate_limit_hours,
            # Timestamps
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class WhatsAppInstance(Base):
    """WhatsApp bot instance with individual configuration"""

    __tablename__ = "whatsapp_instances"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # slug like "support-wa"
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    auto_start: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )

    # WhatsApp Cloud API credentials
    phone_number_id: Mapped[str] = mapped_column(String(50), default="")
    waba_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    access_token: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    verify_token: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    app_secret: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Webhook settings
    webhook_port: Mapped[int] = mapped_column(Integer, default=8003)

    # AI configuration
    llm_backend: Mapped[str] = mapped_column(String(50), default="vllm")
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_params: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    # TTS configuration (voice replies)
    tts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    tts_engine: Mapped[str] = mapped_column(String(20), default="xtts")
    tts_voice: Mapped[str] = mapped_column(String(50), default="anna")
    tts_preset: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Access control
    allowed_phones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    blocked_phones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array

    # RAG configuration
    rag_mode: Mapped[str] = mapped_column(String(20), default="all", server_default="all")
    knowledge_collection_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("knowledge_collections.id"), nullable=True
    )
    knowledge_collection_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Rate limiting
    rate_limit_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rate_limit_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Timestamps
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def get_allowed_phones(self) -> List[str]:
        if not self.allowed_phones:
            return []
        try:
            result: List[str] = json.loads(self.allowed_phones)
            return result
        except (json.JSONDecodeError, TypeError):
            return []

    def set_allowed_phones(self, phones: List[str]) -> None:
        self.allowed_phones = json.dumps(phones)

    def get_blocked_phones(self) -> List[str]:
        if not self.blocked_phones:
            return []
        try:
            result: List[str] = json.loads(self.blocked_phones)
            return result
        except (json.JSONDecodeError, TypeError):
            return []

    def set_blocked_phones(self, phones: List[str]) -> None:
        self.blocked_phones = json.dumps(phones)

    def get_llm_params(self) -> dict:
        if not self.llm_params:
            return {}
        try:
            result: dict = json.loads(self.llm_params)
            return result
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_llm_params(self, params: dict) -> None:
        self.llm_params = json.dumps(params, ensure_ascii=False)

    def to_dict(self, include_token: bool = False) -> dict:
        result = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "auto_start": self.auto_start,
            # WhatsApp API
            "phone_number_id": self.phone_number_id,
            "waba_id": self.waba_id,
            "access_token_masked": "***" + self.access_token[-4:]
            if self.access_token and len(self.access_token) > 4
            else "",
            "verify_token": self.verify_token,
            # Webhook
            "webhook_port": self.webhook_port,
            # AI
            "llm_backend": self.llm_backend,
            "system_prompt": self.system_prompt,
            "llm_params": self.get_llm_params(),
            # TTS
            "tts_enabled": self.tts_enabled,
            "tts_engine": self.tts_engine,
            "tts_voice": self.tts_voice,
            "tts_preset": self.tts_preset,
            # Access control
            "allowed_phones": self.get_allowed_phones(),
            "blocked_phones": self.get_blocked_phones(),
            # RAG
            "rag_mode": self.rag_mode,
            "knowledge_collection_id": self.knowledge_collection_id,
            "knowledge_collection_ids": json.loads(self.knowledge_collection_ids)
            if self.knowledge_collection_ids
            else None,
            # Rate limiting
            "rate_limit_count": self.rate_limit_count,
            "rate_limit_hours": self.rate_limit_hours,
            # Timestamps
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }
        if include_token and self.access_token:
            result["access_token"] = self.access_token
            result["app_secret"] = self.app_secret
        return result


class CloudLLMProvider(Base):
    """Cloud LLM provider configuration (Gemini, Kimi, OpenAI, Claude, custom)"""

    __tablename__ = "cloud_llm_providers"

    id: Mapped[str] = mapped_column(
        String(50), primary_key=True
    )  # slug: "gemini-default", "kimi-prod"
    name: Mapped[str] = mapped_column(String(100), index=True)  # Display: "Gemini Pro", "Kimi K2"
    provider_type: Mapped[str] = mapped_column(
        String(50), index=True
    )  # gemini, kimi, openai, claude, custom

    # Credentials
    api_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    base_url: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )  # e.g., https://api.moonshot.ai/v1
    model_name: Mapped[str] = mapped_column(
        String(100), default=""
    )  # e.g., kimi-k2, gemini-2.0-flash

    # Status
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )

    # Extended configuration (JSON)
    config: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON: temperature, max_tokens, etc.

    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def get_config(self) -> dict:
        """Get extended config as dict"""
        if not self.config:
            return {}
        try:
            result: dict = json.loads(self.config)
            return result
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_config(self, config: dict) -> None:
        """Set extended config from dict"""
        self.config = json.dumps(config, ensure_ascii=False)

    def to_dict(self, include_key: bool = False) -> dict:
        """Convert to dict for API response"""
        result = {
            "id": self.id,
            "name": self.name,
            "provider_type": self.provider_type,
            "api_key_masked": "***" + self.api_key[-4:]
            if self.api_key and len(self.api_key) > 4
            else "",
            "base_url": self.base_url,
            "model_name": self.model_name,
            "enabled": self.enabled,
            "is_default": self.is_default,
            "config": self.get_config(),
            "description": self.description,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }
        if include_key and self.api_key:
            result["api_key"] = self.api_key
        return result


# Provider types configuration
PROVIDER_TYPES = {
    "gemini": {
        "name": "Google Gemini",
        "default_base_url": None,  # Uses SDK
        "default_models": ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro"],
        "requires_base_url": False,
    },
    "kimi": {
        "name": "Moonshot Kimi",
        "default_base_url": "https://api.moonshot.ai/v1",
        "default_models": ["kimi-k2", "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "requires_base_url": True,
    },
    "openai": {
        "name": "OpenAI",
        "default_base_url": "https://api.openai.com/v1",
        "default_models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
        "requires_base_url": True,
    },
    "claude": {
        "name": "Anthropic Claude",
        "default_base_url": "https://api.anthropic.com/v1",
        "default_models": ["claude-opus-4-5-20251101", "claude-sonnet-4-20250514"],
        "requires_base_url": True,
    },
    "deepseek": {
        "name": "DeepSeek",
        "default_base_url": "https://api.deepseek.com/v1",
        "default_models": ["deepseek-chat", "deepseek-coder"],
        "requires_base_url": True,
    },
    "openrouter": {
        "name": "OpenRouter",
        "default_base_url": "https://openrouter.ai/api/v1",
        "default_models": [
            "anthropic/claude-sonnet-4.6",
            "openai/gpt-4o",
            "google/gemini-2.5-pro",
            "google/gemini-2.5-flash",
            "deepseek/deepseek-chat-v3-0324",
            "openai/gpt-4o-mini",
            "qwen/qwen3-235b-a22b",
            "google/gemini-2.0-flash-001",
            "meta-llama/llama-4-maverick",
        ],
        "requires_base_url": True,
    },
    "custom": {
        "name": "Custom OpenAI-Compatible",
        "default_base_url": "",
        "default_models": [],
        "requires_base_url": True,
    },
    "claude_bridge": {
        "name": "Claude Bridge (Local CLI)",
        "default_base_url": "http://127.0.0.1:8787",
        "default_models": ["sonnet", "opus", "haiku"],
        "requires_base_url": False,
    },
}


# Default action buttons for Telegram bots (sales funnel)
# These match the keyboard layout in telegram_bot/sales/keyboards.py
DEFAULT_ACTION_BUTTONS = [
    {
        "id": "diy",
        "label": "Установить самостоятельно",
        "icon": "📦",
        "enabled": True,
        "order": 1,
        "row": 0,  # First row (single button)
        "llm_backend": None,
        "system_prompt": None,
        "llm_params": None,
    },
    {
        "id": "pay_5k",
        "label": "Оплата 5К",
        "icon": "💳",
        "enabled": True,
        "order": 2,
        "row": 1,  # Second row (3 buttons)
        "llm_backend": None,
        "system_prompt": None,
        "llm_params": None,
    },
    {
        "id": "support",
        "label": "Техподдержка",
        "icon": "🛠️",
        "enabled": True,
        "order": 3,
        "row": 1,
        "llm_backend": None,
        "system_prompt": None,
        "llm_params": None,
    },
    {
        "id": "wiki",
        "label": "Wiki",
        "icon": "📚",
        "enabled": True,
        "order": 4,
        "row": 1,
        "llm_backend": None,
        "system_prompt": None,
        "llm_params": None,
    },
    {
        "id": "ask",
        "label": "Задать вопрос",
        "icon": "❓",
        "enabled": True,
        "order": 5,
        "row": 2,  # Third row (3 buttons)
        "llm_backend": None,
        "system_prompt": (
            "Ты - AI-ассистент проекта AI Secretary. "
            "Отвечай на вопросы пользователей об установке, настройке, функционале системы. "
            "Будь полезен и конкретен."
        ),
        "llm_params": {"temperature": 0.7},
    },
    {
        "id": "news",
        "label": "Новости",
        "icon": "📰",
        "enabled": True,
        "order": 6,
        "row": 2,
        "llm_backend": None,
        "system_prompt": None,
        "llm_params": None,
    },
    {
        "id": "start",
        "label": "Старт",
        "icon": "🚀",
        "enabled": True,
        "order": 7,
        "row": 2,
        "llm_backend": None,
        "system_prompt": None,
        "llm_params": None,
    },
    {
        "id": "tz_calc",
        "label": "Рассчитать заказ",
        "icon": "📋",
        "enabled": True,
        "order": 8,
        "row": 3,  # Fourth row (single button)
        "llm_backend": None,
        "system_prompt": (
            "Ты - специалист по составлению технических заданий. "
            "Помоги пользователю сформулировать и структурировать ТЗ для проекта. "
            "Задавай уточняющие вопросы о целях, функционале, технических требованиях."
        ),
        "llm_params": {"temperature": 0.3, "max_tokens": 2048},
    },
]


class PaymentLog(Base):
    """Payment transaction log for Telegram bot payments."""

    __tablename__ = "payment_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    payment_type: Mapped[str] = mapped_column(String(20))  # "yookassa" | "stars"
    product_id: Mapped[str] = mapped_column(String(100))
    amount: Mapped[int] = mapped_column(Integer)  # kopecks for RUB, stars for XTR
    currency: Mapped[str] = mapped_column(String(10))  # "RUB" | "XTR"
    telegram_payment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    provider_payment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="completed")
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "user_id": self.user_id,
            "username": self.username,
            "payment_type": self.payment_type,
            "product_id": self.product_id,
            "amount": self.amount,
            "currency": self.currency,
            "telegram_payment_id": self.telegram_payment_id,
            "provider_payment_id": self.provider_payment_id,
            "status": self.status,
            "created": self.created.isoformat() if self.created else None,
        }


class LLMPreset(Base):
    """LLM preset configuration for vLLM (generation parameters + system prompt)"""

    __tablename__ = "llm_presets"

    id: Mapped[str] = mapped_column(
        String(50), primary_key=True
    )  # slug: "anna", "marina", "creative"
    name: Mapped[str] = mapped_column(String(100), index=True)  # Display name
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # System prompt
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Generation parameters
    temperature: Mapped[float] = mapped_column(default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, default=512)
    top_p: Mapped[float] = mapped_column(default=0.9)
    repetition_penalty: Mapped[float] = mapped_column(default=1.1)

    # Status
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Timestamps
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "repetition_penalty": self.repetition_penalty,
            "is_default": self.is_default,
            "enabled": self.enabled,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }

    def get_params(self) -> dict:
        """Get generation parameters as dict"""
        return {
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "repetition_penalty": self.repetition_penalty,
        }


# Default LLM presets (synced with SECRETARY_PERSONAS from vllm_llm_service.py)
DEFAULT_LLM_PRESETS = [
    {
        "id": "anna",
        "name": "Анна",
        "description": "Анна - дружелюбная и профессиональная секретарь компании Shareware Digital",
        "system_prompt": (
            "Ты — Анна, цифровой секретарь компании Shareware Digital "
            "и личный помощник Артёма Юрьевича.\n\n"
            "ПРАВИЛА:\n"
            "1. Отвечай кратко (2-3 предложения максимум)\n"
            "2. Никакой разметки - только чистый текст\n"
            '3. Используй букву "ё" (всё, идёт, пришлёт)\n'
            "4. Числа пиши словами (пятьсот рублей)\n"
            '5. ООО произноси как "о-о-о", IT как "ай-ти"\n\n'
            "РОЛЬ:\n"
            "- Фильтруй спам и продажи\n"
            "- Записывай сообщения для Артёма Юрьевича\n"
            "- Будь профессиональной и дружелюбной\n\n"
            "ПРИМЕРЫ:\n"
            '- "Здравствуйте! Компания Шэарвэар Диджитал, помощник Артёма Юрьевича, Анна. '
            'Слушаю вас."\n'
            '- "Принято. Я передам Артёму Юрьевичу, что вы звонили."\n'
            '- "К сожалению, это предложение сейчас не актуально. Всего доброго."'
        ),
        "temperature": 0.7,
        "max_tokens": 512,
        "top_p": 0.9,
        "repetition_penalty": 1.1,
        "is_default": True,
    },
    {
        "id": "marina",
        "name": "Марина",
        "description": "Марина - строгая и формальная секретарь компании Shareware Digital",
        "system_prompt": (
            "Ты — Марина, цифровой секретарь компании Shareware Digital "
            "и личный помощник Артёма Юрьевича.\n\n"
            "ПРАВИЛА:\n"
            "1. Отвечай кратко (2-3 предложения максимум)\n"
            "2. Никакой разметки - только чистый текст\n"
            '3. Используй букву "ё" (всё, идёт, пришлёт)\n'
            "4. Числа пиши словами (пятьсот рублей)\n"
            '5. ООО произноси как "о-о-о", IT как "ай-ти"\n\n'
            "РОЛЬ:\n"
            "- Фильтруй спам и продажи\n"
            "- Записывай сообщения для Артёма Юрьевича\n"
            "- Будь профессиональной и дружелюбной\n\n"
            "ПРИМЕРЫ:\n"
            '- "Здравствуйте! Компания Шэарвэар Диджитал, помощник Артёма Юрьевича, Марина. '
            'Слушаю вас."\n'
            '- "Принято. Я передам Артёму Юрьевичу, что вы звонили."\n'
            '- "К сожалению, это предложение сейчас не актуально. Всего доброго."'
        ),
        "temperature": 0.5,
        "max_tokens": 512,
        "top_p": 0.85,
        "repetition_penalty": 1.15,
        "is_default": False,
    },
]


# =============================================================================
# Sales Bot Models
# =============================================================================


class BotAgentPrompt(Base):
    """LLM agent prompt per bot instance and context (segment, funnel stage)."""

    __tablename__ = "bot_agent_prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    prompt_key: Mapped[str] = mapped_column(String(50), index=True)  # welcome, diy_techie, etc.
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text)
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, default=1024)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    order: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (Index("ix_bot_agent_prompts_bot_key", "bot_id", "prompt_key", unique=True),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "prompt_key": self.prompt_key,
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "enabled": self.enabled,
            "order": self.order,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class BotQuizQuestion(Base):
    """Segmentation quiz question with answer options."""

    __tablename__ = "bot_quiz_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    question_key: Mapped[str] = mapped_column(String(50))  # tech_level, infrastructure
    text: Mapped[str] = mapped_column(Text)
    order: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    options: Mapped[str] = mapped_column(
        Text
    )  # JSON: [{"label": "...", "value": "...", "icon": ""}]
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (Index("ix_bot_quiz_questions_bot_key", "bot_id", "question_key"),)

    def get_options(self) -> List[dict]:
        try:
            result: List[dict] = json.loads(self.options) if self.options else []
            return result
        except (json.JSONDecodeError, TypeError):
            return []

    def set_options(self, opts: List[dict]) -> None:
        self.options = json.dumps(opts, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "question_key": self.question_key,
            "text": self.text,
            "order": self.order,
            "enabled": self.enabled,
            "options": self.get_options(),
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class BotSegment(Base):
    """User segment definition with routing rules."""

    __tablename__ = "bot_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    segment_key: Mapped[str] = mapped_column(String(50))  # diy_ready, basic_hot, custom_warm
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    path: Mapped[str] = mapped_column(String(20))  # diy, basic, custom
    match_rules: Mapped[str] = mapped_column(
        Text
    )  # JSON: {"tech_level": "diy", "infrastructure": "gpu"}
    priority: Mapped[int] = mapped_column(Integer, default=0)
    agent_prompt_key: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_bot_segments_bot_key", "bot_id", "segment_key", unique=True),)

    def get_match_rules(self) -> dict:
        try:
            result: dict = json.loads(self.match_rules) if self.match_rules else {}
            return result
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_match_rules(self, rules: dict) -> None:
        self.match_rules = json.dumps(rules, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "segment_key": self.segment_key,
            "name": self.name,
            "description": self.description,
            "path": self.path,
            "match_rules": self.get_match_rules(),
            "priority": self.priority,
            "agent_prompt_key": self.agent_prompt_key,
            "enabled": self.enabled,
            "created": self.created.isoformat() if self.created else None,
        }


class BotUserProfile(Base):
    """User profile with FSM state, segment, quiz answers."""

    __tablename__ = "bot_user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # FSM state
    state: Mapped[str] = mapped_column(String(50), default="new")  # new, quiz_tech, idle, etc.
    segment: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # diy_ready, basic_hot
    path: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # diy, basic, custom

    # Quiz / discovery data
    quiz_answers: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    discovery_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    custom_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON extra data

    # Referral tracking
    ref_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # deeplink param

    # Follow-up control
    followup_optout: Mapped[bool] = mapped_column(Boolean, default=False)
    followup_ignore_count: Mapped[int] = mapped_column(Integer, default=0)
    last_followup_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Activity
    last_activity: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_bot_user_profiles_bot_user", "bot_id", "user_id", unique=True),
        Index("ix_bot_user_profiles_segment", "bot_id", "segment"),
        Index("ix_bot_user_profiles_state", "bot_id", "state"),
    )

    def _get_json(self, field: str) -> dict:
        val = getattr(self, field)
        if not val:
            return {}
        try:
            result: dict = json.loads(val)
            return result
        except (json.JSONDecodeError, TypeError):
            return {}

    def _set_json(self, field: str, data: dict) -> None:
        setattr(self, field, json.dumps(data, ensure_ascii=False))

    def get_quiz_answers(self) -> dict:
        return self._get_json("quiz_answers")

    def set_quiz_answers(self, data: dict) -> None:
        self._set_json("quiz_answers", data)

    def get_discovery_data(self) -> dict:
        return self._get_json("discovery_data")

    def set_discovery_data(self, data: dict) -> None:
        self._set_json("discovery_data", data)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "user_id": self.user_id,
            "username": self.username,
            "first_name": self.first_name,
            "state": self.state,
            "segment": self.segment,
            "path": self.path,
            "quiz_answers": self.get_quiz_answers(),
            "discovery_data": self.get_discovery_data(),
            "ref_source": self.ref_source,
            "followup_optout": self.followup_optout,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class BotFollowupRule(Base):
    """Automated follow-up trigger rule."""

    __tablename__ = "bot_followup_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(100))
    trigger: Mapped[str] = mapped_column(String(50))  # clicked_github_no_return, inactive_7_days
    delay_hours: Mapped[int] = mapped_column(Integer, default=24)
    segment_filter: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # diy, basic, all
    message_template: Mapped[str] = mapped_column(Text)
    buttons: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON: [{"text","callback"}]
    max_sends: Mapped[int] = mapped_column(Integer, default=2)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    order: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def get_buttons(self) -> List[dict]:
        if not self.buttons:
            return []
        try:
            result: List[dict] = json.loads(self.buttons)
            return result
        except (json.JSONDecodeError, TypeError):
            return []

    def set_buttons(self, btns: List[dict]) -> None:
        self.buttons = json.dumps(btns, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "name": self.name,
            "trigger": self.trigger,
            "delay_hours": self.delay_hours,
            "segment_filter": self.segment_filter,
            "message_template": self.message_template,
            "buttons": self.get_buttons(),
            "max_sends": self.max_sends,
            "enabled": self.enabled,
            "order": self.order,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class BotFollowupQueue(Base):
    """Pending follow-up message in queue."""

    __tablename__ = "bot_followup_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    rule_id: Mapped[int] = mapped_column(Integer, index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )  # pending, sent, cancelled, failed
    send_count: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_bot_followup_queue_pending", "status", "scheduled_at"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "user_id": self.user_id,
            "rule_id": self.rule_id,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "status": self.status,
            "send_count": self.send_count,
            "created": self.created.isoformat() if self.created else None,
        }


class BotEvent(Base):
    """Funnel event tracking for analytics."""

    __tablename__ = "bot_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    event_type: Mapped[str] = mapped_column(
        String(50), index=True
    )  # start, quiz_completed, cta_clicked
    event_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (Index("ix_bot_events_bot_type_created", "bot_id", "event_type", "created"),)

    def get_event_data(self) -> dict:
        if not self.event_data:
            return {}
        try:
            result: dict = json.loads(self.event_data)
            return result
        except (json.JSONDecodeError, TypeError):
            return {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "user_id": self.user_id,
            "event_type": self.event_type,
            "event_data": self.get_event_data(),
            "created": self.created.isoformat() if self.created else None,
        }


class BotTestimonial(Base):
    """Social proof testimonial."""

    __tablename__ = "bot_testimonials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    text: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(100), default="***")  # anonymized
    rating: Mapped[int] = mapped_column(Integer, default=5)  # 1-5
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    order: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "text": self.text,
            "author": self.author,
            "rating": self.rating,
            "enabled": self.enabled,
            "order": self.order,
            "created": self.created.isoformat() if self.created else None,
        }


class BotHardwareSpec(Base):
    """GPU model capabilities for hardware audit."""

    __tablename__ = "bot_hardware_specs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    gpu_name: Mapped[str] = mapped_column(String(100))  # RTX 3060, GTX 1660
    gpu_vram_gb: Mapped[int] = mapped_column(Integer)  # 6, 8, 12, 24
    gpu_family: Mapped[str] = mapped_column(String(50))  # gtx_16xx, rtx_30xx, rtx_40xx
    recommended_llm: Mapped[str] = mapped_column(String(100))  # Qwen2.5-7B, Qwen-14B
    recommended_tts: Mapped[str] = mapped_column(String(50))  # xtts, piper, openvoice
    recommended_stt: Mapped[str] = mapped_column(String(50), default="whisper")
    quality_stars: Mapped[int] = mapped_column(Integer, default=3)  # 1-5
    speed_note: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    order: Mapped[int] = mapped_column(Integer, default=0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "gpu_name": self.gpu_name,
            "gpu_vram_gb": self.gpu_vram_gb,
            "gpu_family": self.gpu_family,
            "recommended_llm": self.recommended_llm,
            "recommended_tts": self.recommended_tts,
            "recommended_stt": self.recommended_stt,
            "quality_stars": self.quality_stars,
            "speed_note": self.speed_note,
            "notes": self.notes,
            "enabled": self.enabled,
            "order": self.order,
        }


class BotAbTest(Base):
    """A/B test definition."""

    __tablename__ = "bot_ab_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(100))
    test_key: Mapped[str] = mapped_column(String(50))  # welcome_message, urgency_slots
    variants: Mapped[str] = mapped_column(Text)  # JSON: {"A": {...}, "B": {...}}
    metric: Mapped[str] = mapped_column(String(50))  # quiz_completion_rate, checkout_conversion
    min_sample: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    results: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON: per-variant stats
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (Index("ix_bot_ab_tests_bot_key", "bot_id", "test_key"),)

    def get_variants(self) -> dict:
        try:
            result: dict = json.loads(self.variants) if self.variants else {}
            return result
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_variants(self, data: dict) -> None:
        self.variants = json.dumps(data, ensure_ascii=False)

    def get_results(self) -> dict:
        if not self.results:
            return {}
        try:
            result: dict = json.loads(self.results)
            return result
        except (json.JSONDecodeError, TypeError):
            return {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "name": self.name,
            "test_key": self.test_key,
            "variants": self.get_variants(),
            "metric": self.metric,
            "min_sample": self.min_sample,
            "active": self.active,
            "results": self.get_results(),
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class BotDiscoveryResponse(Base):
    """User's answers from custom path discovery flow."""

    __tablename__ = "bot_discovery_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    step: Mapped[int] = mapped_column(Integer)  # 1-5
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)  # free text or selected value
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_bot_discovery_bot_user", "bot_id", "user_id"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "user_id": self.user_id,
            "step": self.step,
            "question": self.question,
            "answer": self.answer,
            "created": self.created.isoformat() if self.created else None,
        }


class BotSubscriber(Base):
    """News/updates subscription for Telegram users."""

    __tablename__ = "bot_subscribers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    subscribed: Mapped[bool] = mapped_column(Boolean, default=True)
    subscribed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    unsubscribed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_bot_subscribers_bot_user", "bot_id", "user_id", unique=True),
        Index("ix_bot_subscribers_active", "bot_id", "subscribed"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "user_id": self.user_id,
            "subscribed": self.subscribed,
            "subscribed_at": self.subscribed_at.isoformat() if self.subscribed_at else None,
            "unsubscribed_at": self.unsubscribed_at.isoformat() if self.unsubscribed_at else None,
        }


class BotGithubConfig(Base):
    """GitHub webhook + PR comment configuration per bot instance."""

    __tablename__ = "bot_github_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    repo_owner: Mapped[str] = mapped_column(String(100), default="ShaerWare")
    repo_name: Mapped[str] = mapped_column(String(100), default="AI_Secretary_System")
    github_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    comment_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    broadcast_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    comment_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    broadcast_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    events: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON: ["opened","merged"]
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def get_events(self) -> List[str]:
        if not self.events:
            return ["opened", "merged"]
        try:
            result: List[str] = json.loads(self.events)
            return result
        except (json.JSONDecodeError, TypeError):
            return ["opened", "merged"]

    def set_events(self, evts: List[str]) -> None:
        self.events = json.dumps(evts)

    def to_dict(self, include_token: bool = False) -> dict:
        result: dict[str, Any] = {
            "id": self.id,
            "bot_id": self.bot_id,
            "repo_owner": self.repo_owner,
            "repo_name": self.repo_name,
            "github_token_masked": "***" + self.github_token[-4:]
            if self.github_token and len(self.github_token) > 4
            else "",
            "webhook_secret_masked": "***" if self.webhook_secret else "",
            "comment_enabled": self.comment_enabled,
            "broadcast_enabled": self.broadcast_enabled,
            "comment_prompt": self.comment_prompt,
            "broadcast_prompt": self.broadcast_prompt,
            "events": self.get_events(),
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }
        if include_token:
            result["github_token"] = self.github_token
            result["webhook_secret"] = self.webhook_secret
        return result


class UsageLog(Base):
    """Usage tracking for TTS/STT/LLM operations."""

    __tablename__ = "usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    service_type: Mapped[str] = mapped_column(String(20), index=True)  # "tts", "stt", "llm"
    action: Mapped[str] = mapped_column(String(50))  # "synthesis", "transcribe", "chat"
    source: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, index=True
    )  # "admin", "telegram", "widget"
    source_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # Usage metrics (tokens for LLM, characters for TTS, seconds for STT)
    units_consumed: Mapped[int] = mapped_column(Integer, default=1)
    cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Additional details
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    # Indexes for common queries
    __table_args__ = (
        Index("ix_usage_log_service_timestamp", "service_type", "timestamp"),
        Index("ix_usage_log_source_timestamp", "source", "timestamp"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "service_type": self.service_type,
            "action": self.action,
            "source": self.source,
            "source_id": self.source_id,
            "units_consumed": self.units_consumed,
            "cost_usd": self.cost_usd,
            "details": json.loads(self.details) if self.details else None,
        }


class UsageLimits(Base):
    """Usage limits and quotas configuration."""

    __tablename__ = "usage_limits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_type: Mapped[str] = mapped_column(
        String(20),
    )  # "tts", "stt", "llm"# "tts", "stt", "llm"
    limit_type: Mapped[str] = mapped_column(String(20))  # "daily", "monthly", "per_request"
    limit_value: Mapped[int] = mapped_column(Integer)  # units per period
    warning_threshold: Mapped[int] = mapped_column(Integer, default=80)  # % to warn at
    hard_limit: Mapped[bool] = mapped_column(Boolean, default=False)  # enforced or soft warning
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Unique constraint on service_type + limit_type
    __table_args__ = (
        Index("ix_usage_limits_service_type", "service_type", "limit_type", unique=True),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "service_type": self.service_type,
            "limit_type": self.limit_type,
            "limit_value": self.limit_value,
            "warning_threshold": self.warning_threshold,
            "hard_limit": self.hard_limit,
            "enabled": self.enabled,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class UserConsent(Base):
    """User consent records for GDPR/legal compliance."""

    __tablename__ = "user_consents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(100), index=True)  # telegram_id, session_id, etc.
    user_type: Mapped[str] = mapped_column(String(20))  # "telegram", "widget", "admin"
    consent_type: Mapped[str] = mapped_column(
        String(50), index=True
    )  # "privacy_policy", "voice_recording", "data_processing", "call_recording"
    consent_version: Mapped[str] = mapped_column(String(20), default="1.0")
    granted: Mapped[bool] = mapped_column(Boolean, default=False)
    granted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)  # IPv6 max length
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Unique constraint on user_id + consent_type
    __table_args__ = (Index("ix_user_consents_user_type", "user_id", "consent_type", unique=True),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_type": self.user_type,
            "consent_type": self.consent_type,
            "consent_version": self.consent_version,
            "granted": self.granted,
            "granted_at": self.granted_at.isoformat() if self.granted_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "ip_address": self.ip_address,
            "created": self.created.isoformat() if self.created else None,
        }


# Consent types enum-like constants
CONSENT_TYPES = {
    "privacy_policy": {
        "name": "Политика конфиденциальности",
        "name_en": "Privacy Policy",
        "required": True,
        "description": "Согласие на обработку персональных данных",
    },
    "voice_recording": {
        "name": "Запись голоса",
        "name_en": "Voice Recording",
        "required": False,
        "description": "Согласие на запись и обработку голоса для TTS/STT",
    },
    "call_recording": {
        "name": "Запись звонков",
        "name_en": "Call Recording",
        "required": False,
        "description": "Согласие на запись телефонных разговоров",
    },
    "data_processing": {
        "name": "Обработка данных",
        "name_en": "Data Processing",
        "required": True,
        "description": "Согласие на обработку данных для работы сервиса",
    },
    "marketing": {
        "name": "Маркетинговые коммуникации",
        "name_en": "Marketing Communications",
        "required": False,
        "description": "Согласие на получение рекламных материалов",
    },
}


# =============================================================================
# amoCRM Integration
# =============================================================================


class AmoCRMConfig(Base):
    """amoCRM integration configuration and OAuth tokens (singleton, id=1)."""

    __tablename__ = "amocrm_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # User-entered settings (via admin panel)
    subdomain: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    client_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    client_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    redirect_uri: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # OAuth tokens (managed by service)
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Sync settings
    sync_contacts: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_leads: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_tasks: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_create_lead: Mapped[bool] = mapped_column(Boolean, default=True)
    lead_pipeline_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lead_status_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Webhook
    webhook_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Amojo (chat messaging) settings
    amojo_base_url: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default="https://amojo.amocrm.ru"
    )
    amojo_scope_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    amojo_channel_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Stats
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    contacts_count: Mapped[int] = mapped_column(Integer, default=0)
    leads_count: Mapped[int] = mapped_column(Integer, default=0)

    # Metadata
    account_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def get_account_info(self) -> dict[str, Any]:
        if not self.account_info:
            return {}
        try:
            result: dict[str, Any] = json.loads(self.account_info)
            return result
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_account_info(self, info: dict) -> None:
        self.account_info = json.dumps(info, ensure_ascii=False)

    def is_connected(self) -> bool:
        return bool(self.access_token and self.refresh_token)

    def is_token_expired(self) -> bool:
        if not self.token_expires_at:
            return True
        return datetime.utcnow() >= self.token_expires_at

    def to_dict(self, include_secrets: bool = False) -> dict:
        result: dict[str, Any] = {
            "id": self.id,
            "subdomain": self.subdomain,
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "is_connected": self.is_connected(),
            "sync_contacts": self.sync_contacts,
            "sync_leads": self.sync_leads,
            "sync_tasks": self.sync_tasks,
            "auto_create_lead": self.auto_create_lead,
            "lead_pipeline_id": self.lead_pipeline_id,
            "lead_status_id": self.lead_status_id,
            "webhook_url": self.webhook_url,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "contacts_count": self.contacts_count,
            "leads_count": self.leads_count,
            "account_info": self.get_account_info(),
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }
        # Amojo fields
        result["amojo_base_url"] = self.amojo_base_url or "https://amojo.amocrm.ru"
        result["amojo_scope_id"] = self.amojo_scope_id
        result["amojo_inbox_configured"] = bool(self.amojo_scope_id and self.amojo_channel_secret)

        if include_secrets:
            result["client_secret"] = self.client_secret
            result["amojo_channel_secret"] = self.amojo_channel_secret
        else:
            result["client_secret_masked"] = (
                "***" + self.client_secret[-4:]
                if self.client_secret and len(self.client_secret) > 4
                else ""
            )
        return result


class AmoCRMSyncLog(Base):
    """amoCRM sync event log."""

    __tablename__ = "amocrm_sync_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    direction: Mapped[str] = mapped_column(String(20))  # "incoming" or "outgoing"
    entity_type: Mapped[str] = mapped_column(String(50))  # "contact", "lead", "task"
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(20))  # "create", "update", "delete", "sync"
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    status: Mapped[str] = mapped_column(String(20), default="success")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (Index("ix_amocrm_sync_log_entity", "entity_type", "entity_id"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "direction": self.direction,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "action": self.action,
            "details": json.loads(self.details) if self.details else None,
            "status": self.status,
            "error_message": self.error_message,
            "created": self.created.isoformat() if self.created else None,
        }


# =============================================================================
# WooCommerce Integration
# =============================================================================


class WooCommerceConfig(Base):
    """WooCommerce store connection config (singleton, id=1)."""

    __tablename__ = "woocommerce_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_url: Mapped[str] = mapped_column(String(500), default="")
    consumer_key: Mapped[str] = mapped_column(String(500), default="")
    consumer_secret: Mapped[str] = mapped_column(String(500), default="")
    is_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    products_count: Mapped[int] = mapped_column(Integer, default=0)
    categories_count: Mapped[int] = mapped_column(Integer, default=0)
    orders_count: Mapped[int] = mapped_column(Integer, default=0)
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id"), default=1)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def to_dict(self, include_secrets: bool = False) -> dict:
        result: dict = {
            "id": self.id,
            "store_url": self.store_url,
            "is_connected": self.is_connected,
            "sync_enabled": self.sync_enabled,
            "last_sync_at": self.last_sync_at,
            "products_count": self.products_count,
            "categories_count": self.categories_count,
            "orders_count": self.orders_count,
            "workspace_id": self.workspace_id,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }
        if include_secrets:
            result["consumer_key"] = self.consumer_key
            result["consumer_secret"] = self.consumer_secret
        else:
            result["consumer_key_masked"] = (
                "***" + self.consumer_key[-4:]
                if self.consumer_key and len(self.consumer_key) > 4
                else ""
            )
            result["consumer_secret_masked"] = (
                "***" + self.consumer_secret[-4:]
                if self.consumer_secret and len(self.consumer_secret) > 4
                else ""
            )
        return result


# =============================================================================
# GitHub Repository Projects (Knowledge Base)
# =============================================================================

# Default file patterns for GitHub repo sync
GITHUB_DEFAULT_INCLUDE = [
    "*.md",
    "*.py",
    "*.ts",
    "*.tsx",
    "*.vue",
    "*.go",
    "*.js",
    "*.jsx",
    "*.rs",
    "*.java",
    "*.yaml",
    "*.yml",
    "*.toml",
    "*.sh",
    "*.sql",
    "*.html",
    "*.css",
]
GITHUB_DEFAULT_EXCLUDE = [
    "node_modules",
    ".git",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "*.lock",
    "*.min.js",
    "*.min.css",
    "package-lock.json",
]


class GitHubRepoProject(Base):
    """GitHub repository connected as a knowledge base collection."""

    __tablename__ = "github_repo_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    github_owner: Mapped[str] = mapped_column(String(100), nullable=False)
    github_repo: Mapped[str] = mapped_column(String(100), nullable=False)
    github_token: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    branch: Mapped[str] = mapped_column(String(100), default="main", server_default="main")
    collection_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("knowledge_collections.id"), nullable=True
    )
    sync_status: Mapped[str] = mapped_column(String(20), default="idle", server_default="idle")
    sync_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_synced: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_commit_sha: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    include_patterns: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    exclude_patterns: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total_size_bytes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    created: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    def get_include_patterns(self) -> list[str]:
        if self.include_patterns:
            try:
                result: list[str] = json.loads(self.include_patterns)
                return result
            except (json.JSONDecodeError, TypeError):
                pass
        return list(GITHUB_DEFAULT_INCLUDE)

    def get_exclude_patterns(self) -> list[str]:
        if self.exclude_patterns:
            try:
                result: list[str] = json.loads(self.exclude_patterns)
                return result
            except (json.JSONDecodeError, TypeError):
                pass
        return list(GITHUB_DEFAULT_EXCLUDE)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "github_owner": self.github_owner,
            "github_repo": self.github_repo,
            "has_token": bool(self.github_token),
            "branch": self.branch,
            "collection_id": self.collection_id,
            "sync_status": self.sync_status,
            "sync_error": self.sync_error,
            "last_synced": self.last_synced.isoformat() if self.last_synced else None,
            "last_commit_sha": self.last_commit_sha,
            "include_patterns": self.get_include_patterns(),
            "exclude_patterns": self.get_exclude_patterns(),
            "file_count": self.file_count,
            "total_size_bytes": self.total_size_bytes,
            "workspace_id": self.workspace_id,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


# =============================================================================
# GSM Telephony
# =============================================================================


class GSMCallLog(Base):
    """GSM call history log."""

    __tablename__ = "gsm_call_logs"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    direction: Mapped[str] = mapped_column(String(10), index=True)  # incoming/outgoing
    state: Mapped[str] = mapped_column(String(20), index=True)
    caller_number: Mapped[str] = mapped_column(String(20), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    transcript_preview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    audio_file_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sms_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "direction": self.direction,
            "state": self.state,
            "caller_number": self.caller_number,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "answered_at": self.answered_at.isoformat() if self.answered_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration_seconds,
            "transcript_preview": self.transcript_preview,
            "sms_sent": self.sms_sent,
        }


class GSMSMSLog(Base):
    """GSM SMS message log."""

    __tablename__ = "gsm_sms_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    direction: Mapped[str] = mapped_column(String(10), index=True)  # incoming/outgoing
    number: Mapped[str] = mapped_column(String(20), index=True)
    text: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    status: Mapped[str] = mapped_column(String(20))  # sent/delivered/failed/received

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "direction": self.direction,
            "number": self.number,
            "text": self.text,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "status": self.status,
        }


# ============== Knowledge Base ==============


class KnowledgeCollection(Base):
    """Knowledge base collection (container for documents)."""

    __tablename__ = "knowledge_collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    base_dir: Mapped[str] = mapped_column(
        String(200), default="wiki-pages", server_default="wiki-pages"
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    created: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    documents: Mapped[list["KnowledgeDocument"]] = relationship(
        "KnowledgeDocument", back_populates="collection", lazy="noload"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "enabled": self.enabled,
            "base_dir": self.base_dir,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class KnowledgeDocument(Base):
    """Knowledge base document tracked in wiki-pages/."""

    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    source_type: Mapped[str] = mapped_column(String(50), default="manual")  # manual, import, wiki
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    section_count: Mapped[int] = mapped_column(Integer, default=0)
    collection_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("knowledge_collections.id"), nullable=True, index=True
    )
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    created: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    collection: Mapped[Optional["KnowledgeCollection"]] = relationship(
        "KnowledgeCollection", back_populates="documents"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "title": self.title,
            "source_type": self.source_type,
            "file_size_bytes": self.file_size_bytes,
            "section_count": self.section_count,
            "collection_id": self.collection_id,
            "owner_id": self.owner_id,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


# =============================================================================
# Default Sales Bot Data (seeded on first migration)
# =============================================================================

DEFAULT_AGENT_PROMPTS = [
    {
        "prompt_key": "welcome",
        "name": "Приветствие",
        "description": "Первое сообщение + social proof + приглашение в квиз",
        "system_prompt": (
            "Ты — AI-ассистент проекта AI Secretary от ShaerWare. "
            "Твоя задача — приветствовать нового пользователя, кратко рассказать о проекте "
            "(голосовой AI на своём сервере, без абонентки, клонирование голоса, работает офлайн), "
            "показать social proof (звёзды GitHub, отзывы) и пригласить пройти "
            "2-минутный квиз для подбора лучшего варианта. "
            "Тон: дружелюбный, уверенный, не навязчивый. Русский язык."
        ),
        "temperature": 0.7,
        "max_tokens": 512,
        "order": 1,
    },
    {
        "prompt_key": "diy_techie",
        "name": "DIY — Технарь",
        "description": "Для технически подкованных пользователей, которые хотят ставить сами",
        "system_prompt": (
            "Ты — технический консультант проекта AI Secretary. "
            "Пользователь — технарь, хочет установить систему самостоятельно. "
            "Давай технические детали: GPU требования, модели LLM, Docker-команды, "
            "конфигурацию. Ссылайся на GitHub (github.com/ShaerWare/AI_Secretary_System) "
            "и вики (github.com/ShaerWare/AI_Secretary_System/wiki). "
            "Предлагай поставить звезду на GitHub если проект полезен. "
            "Тон: технический, конкретный, без воды."
        ),
        "temperature": 0.3,
        "max_tokens": 1024,
        "order": 2,
    },
    {
        "prompt_key": "basic_busy",
        "name": "Basic — Занятой",
        "description": "Для пользователей, которые хотят готовое решение",
        "system_prompt": (
            "Ты — менеджер по продажам проекта AI Secretary. "
            "Пользователь хочет готовое решение, не хочет разбираться в технических деталях. "
            "Фокусируйся на: экономии (vs SaaS-боты 15K₽/мес), простоте установки (30 мин), "
            "приватности данных (152-ФЗ), отсутствии абонентки. "
            "Предлагай услугу установки. Показывай ROI. "
            "Тон: профессиональный, убедительный, с конкретными цифрами."
        ),
        "temperature": 0.7,
        "max_tokens": 768,
        "order": 3,
    },
    {
        "prompt_key": "custom_business",
        "name": "Custom — Бизнес",
        "description": "Для бизнес-клиентов с задачами интеграции",
        "system_prompt": (
            "Ты — бизнес-консультант проекта AI Secretary. "
            "Пользователь — представитель бизнеса, ему нужна кастомная интеграция "
            "(CRM, телефония, кастомные сценарии). "
            "Рассказывай о кейсах: автосалон -70% нагрузки, клиника +40% записей. "
            "Задавай квалифицирующие вопросы: задача, объём, интеграции, бюджет, сроки. "
            "Формируй предварительный расчёт. "
            "Тон: деловой, экспертный, с кейсами."
        ),
        "temperature": 0.5,
        "max_tokens": 1024,
        "order": 4,
    },
    {
        "prompt_key": "faq_answer",
        "name": "FAQ ответ",
        "description": "Точные ответы по документации проекта",
        "system_prompt": (
            "Ты — справочный бот проекта AI Secretary. "
            "Отвечай кратко и точно на вопросы о проекте, опираясь на документацию. "
            "Если не знаешь ответа — честно скажи и предложи посмотреть вики "
            "(github.com/ShaerWare/AI_Secretary_System/wiki) или задать вопрос автору. "
            "Русский язык. Максимум 3-4 предложения."
        ),
        "temperature": 0.2,
        "max_tokens": 512,
        "order": 5,
    },
    {
        "prompt_key": "hardware_audit",
        "name": "Аудит железа",
        "description": "Рекомендация модели LLM/TTS по характеристикам GPU",
        "system_prompt": (
            "Ты — технический эксперт по AI-инфраструктуре. "
            "На основе модели GPU пользователя рекомендуй оптимальную конфигурацию "
            "AI Secretary: модель LLM (Qwen/Llama/DeepSeek), TTS движок (XTTS/Piper), "
            "оценку качества (1-5 звёзд), скорость ответа. "
            "Если GPU слабая — предложи CPU-режим + Cloud LLM. "
            "Формат: структурированный список с emoji."
        ),
        "temperature": 0.2,
        "max_tokens": 768,
        "order": 6,
    },
    {
        "prompt_key": "roi_calculator",
        "name": "ROI калькулятор",
        "description": "Расчёт экономии vs SaaS-решения",
        "system_prompt": (
            "Ты — финансовый консультант. Рассчитай экономию от использования "
            "AI Secretary (self-hosted, разовая оплата 5000₽) vs типичного SaaS-бота "
            "(15000₽/мес). Покажи экономию за 1 год, 3 года. "
            "Добавь бонусы: приватность данных, работа офлайн, кастомизация, клонирование голоса. "
            "Формат: таблица сравнения + итог."
        ),
        "temperature": 0.3,
        "max_tokens": 768,
        "order": 7,
    },
    {
        "prompt_key": "discovery_summary",
        "name": "Итог discovery",
        "description": "Генерация коммерческого предложения по результатам discovery",
        "system_prompt": (
            "Ты — менеджер проектов. На основе ответов discovery-анкеты "
            "(задача, объём, интеграции, сроки, бюджет) сформируй предварительный расчёт. "
            "Укажи: что входит, стоимость каждого компонента, итоговую вилку цен, "
            "сроки реализации. Добавь пометку что это предварительная оценка. "
            "Формат: структурированное КП."
        ),
        "temperature": 0.4,
        "max_tokens": 1024,
        "order": 8,
    },
    {
        "prompt_key": "objection_price",
        "name": "Возражение: дорого",
        "description": "Работа с возражением по цене",
        "system_prompt": (
            "Пользователь считает цену высокой. Предложи альтернативы: "
            "1) MVP-версия без интеграций (дешевле), "
            "2) Поэтапное внедрение (оплата по частям), "
            "3) Self-hosted с консультацией (самый бюджетный). "
            "Не давить, а показать варианты. Тон: понимающий, гибкий."
        ),
        "temperature": 0.6,
        "max_tokens": 768,
        "order": 9,
    },
    {
        "prompt_key": "objection_nogpu",
        "name": "Возражение: нет GPU",
        "description": "Варианты работы без GPU",
        "system_prompt": (
            "У пользователя нет GPU. Предложи 3 варианта: "
            "1) CPU-режим + Cloud LLM (бесплатный tier Gemini), "
            "2) Аренда VPS с GPU (от 3000₽/мес), "
            "3) Свой мини-сервер (RTX 3060 б/у ~25000₽, окупается за 8 мес). "
            "Сравни плюсы и минусы каждого. Тон: помогающий."
        ),
        "temperature": 0.5,
        "max_tokens": 768,
        "order": 10,
    },
    {
        "prompt_key": "followup_gentle",
        "name": "Follow-up мягкий",
        "description": "Мягкое напоминание для follow-up сообщений",
        "system_prompt": (
            "Напиши мягкое follow-up сообщение для пользователя, который давно не заходил. "
            "Расскажи о новых фичах проекта, предложи помощь. "
            "Обязательно дай возможность отписаться. "
            "Максимум 3 предложения. Не навязывай."
        ),
        "temperature": 0.7,
        "max_tokens": 256,
        "order": 11,
    },
    {
        "prompt_key": "pr_comment",
        "name": "Комментарий к PR",
        "description": "AI-саммари для GitHub Pull Request",
        "system_prompt": (
            "Ты — AI-ассистент проекта AI Secretary. "
            "Напиши краткий информативный комментарий к Pull Request на русском. "
            "Формат: заголовок '## 🤖 AI Secretary Bot Summary', "
            "затем секции: 'Что изменилось' (3-5 буллетов), "
            "'Кому важно' (для каких пользователей), "
            "'Breaking changes' (есть или нет). "
            "В конце подпись: *Сгенерировано AI Secretary Bot*."
        ),
        "temperature": 0.3,
        "max_tokens": 1024,
        "order": 12,
    },
    {
        "prompt_key": "pr_news",
        "name": "Новость о PR",
        "description": "Telegram-рассылка о новом PR/обновлении",
        "system_prompt": (
            "Сформируй короткую новость для Telegram-подписчиков о новом обновлении проекта "
            "AI Secretary на основе Pull Request. 2-3 предложения, emoji уместны. "
            "Добавь ссылку на PR. Предложи поставить звезду на GitHub. "
            "Русский язык. Максимум 5 строк."
        ),
        "temperature": 0.6,
        "max_tokens": 256,
        "order": 13,
    },
    {
        "prompt_key": "general_chat",
        "name": "Свободный чат",
        "description": "Общение с AI-ассистентом вне воронки",
        "system_prompt": (
            "Ты — AI-ассистент проекта AI Secretary (github.com/ShaerWare/AI_Secretary_System). "
            "Отвечай на любые вопросы о проекте. Если вопрос не про проект — "
            "вежливо направь обратно. Ссылайся на вики и README. "
            "Автор проекта: github.com/ShaerWare. "
            "Тон: дружелюбный, компетентный."
        ),
        "temperature": 0.7,
        "max_tokens": 1024,
        "order": 14,
    },
]

DEFAULT_QUIZ_QUESTIONS = [
    {
        "question_key": "tech_level",
        "text": "📋 Вопрос 1 из 2\n\nКак вы относитесь к технической стороне?",
        "order": 1,
        "options": [
            {"label": "🛠️ Люблю сам разбираться в настройках", "value": "diy", "icon": "🛠️"},
            {"label": "🤝 Предпочитаю готовое решение", "value": "ready", "icon": "🤝"},
            {
                "label": "🏢 У меня бизнес-задача, нужна интеграция",
                "value": "business",
                "icon": "🏢",
            },
        ],
    },
    {
        "question_key": "infrastructure",
        "text": "📋 Вопрос 2 из 2\n\nЕсть ли у вас сервер для установки?",
        "order": 2,
        "options": [
            {"label": "✅ Да, есть сервер с GPU", "value": "gpu", "icon": "✅"},
            {"label": "💻 Есть сервер, но без GPU", "value": "cpu", "icon": "💻"},
            {"label": "❌ Нет сервера", "value": "none", "icon": "❌"},
            {"label": "🤷 Не знаю / Нужна консультация", "value": "unknown", "icon": "🤷"},
        ],
    },
]

DEFAULT_SEGMENTS = [
    # DIY path
    {
        "segment_key": "diy_ready",
        "name": "DIY Ready",
        "path": "diy",
        "match_rules": {"tech_level": "diy", "infrastructure": "gpu"},
        "agent_prompt_key": "diy_techie",
        "priority": 10,
    },
    {
        "segment_key": "diy_need_advice",
        "name": "DIY нужен совет",
        "path": "diy",
        "match_rules": {"tech_level": "diy", "infrastructure": "cpu"},
        "agent_prompt_key": "diy_techie",
        "priority": 9,
    },
    {
        "segment_key": "diy_need_hw",
        "name": "DIY нужно железо",
        "path": "diy",
        "match_rules": {"tech_level": "diy", "infrastructure": "none"},
        "agent_prompt_key": "diy_techie",
        "priority": 8,
    },
    {
        "segment_key": "diy_need_audit",
        "name": "DIY нужен аудит",
        "path": "diy",
        "match_rules": {"tech_level": "diy", "infrastructure": "unknown"},
        "agent_prompt_key": "diy_techie",
        "priority": 7,
    },
    # Basic path
    {
        "segment_key": "basic_hot",
        "name": "🔥 Basic горячий",
        "path": "basic",
        "match_rules": {"tech_level": "ready", "infrastructure": "gpu"},
        "agent_prompt_key": "basic_busy",
        "priority": 10,
    },
    {
        "segment_key": "basic_warm",
        "name": "Basic тёплый",
        "path": "basic",
        "match_rules": {"tech_level": "ready", "infrastructure": "cpu"},
        "agent_prompt_key": "basic_busy",
        "priority": 9,
    },
    {
        "segment_key": "basic_cold",
        "name": "Basic холодный",
        "path": "basic",
        "match_rules": {"tech_level": "ready", "infrastructure": "none"},
        "agent_prompt_key": "basic_busy",
        "priority": 8,
    },
    {
        "segment_key": "basic_audit",
        "name": "Basic аудит",
        "path": "basic",
        "match_rules": {"tech_level": "ready", "infrastructure": "unknown"},
        "agent_prompt_key": "basic_busy",
        "priority": 7,
    },
    # Custom path
    {
        "segment_key": "custom_hot",
        "name": "🔥 Custom горячий",
        "path": "custom",
        "match_rules": {"tech_level": "business", "infrastructure": "gpu"},
        "agent_prompt_key": "custom_business",
        "priority": 10,
    },
    {
        "segment_key": "custom_warm",
        "name": "Custom тёплый",
        "path": "custom",
        "match_rules": {"tech_level": "business", "infrastructure": "cpu"},
        "agent_prompt_key": "custom_business",
        "priority": 9,
    },
    {
        "segment_key": "custom_full",
        "name": "Custom под ключ",
        "path": "custom",
        "match_rules": {"tech_level": "business", "infrastructure": "none"},
        "agent_prompt_key": "custom_business",
        "priority": 10,
    },
    {
        "segment_key": "custom_discovery",
        "name": "Custom discovery",
        "path": "custom",
        "match_rules": {"tech_level": "business", "infrastructure": "unknown"},
        "agent_prompt_key": "custom_business",
        "priority": 8,
    },
]

DEFAULT_HARDWARE_SPECS = [
    {
        "gpu_name": "GTX 1660 Super",
        "gpu_vram_gb": 6,
        "gpu_family": "gtx_16xx",
        "recommended_llm": "Qwen2.5-3B",
        "recommended_tts": "openvoice",
        "quality_stars": 2,
        "speed_note": "~3-5 сек",
        "order": 1,
    },
    {
        "gpu_name": "GTX 1070/1080",
        "gpu_vram_gb": 8,
        "gpu_family": "gtx_10xx",
        "recommended_llm": "Qwen2.5-3B",
        "recommended_tts": "openvoice",
        "quality_stars": 2,
        "speed_note": "~3-4 сек",
        "order": 2,
    },
    {
        "gpu_name": "RTX 3060",
        "gpu_vram_gb": 12,
        "gpu_family": "rtx_30xx",
        "recommended_llm": "Qwen2.5-7B",
        "recommended_tts": "xtts",
        "quality_stars": 3,
        "speed_note": "~2 сек",
        "order": 3,
    },
    {
        "gpu_name": "RTX 3070",
        "gpu_vram_gb": 8,
        "gpu_family": "rtx_30xx",
        "recommended_llm": "Qwen2.5-7B-AWQ",
        "recommended_tts": "xtts",
        "quality_stars": 3,
        "speed_note": "~2 сек",
        "order": 4,
    },
    {
        "gpu_name": "RTX 3080",
        "gpu_vram_gb": 10,
        "gpu_family": "rtx_30xx",
        "recommended_llm": "Qwen2.5-7B",
        "recommended_tts": "xtts",
        "quality_stars": 3,
        "speed_note": "~1.5 сек",
        "order": 5,
    },
    {
        "gpu_name": "RTX 3090",
        "gpu_vram_gb": 24,
        "gpu_family": "rtx_30xx",
        "recommended_llm": "Qwen2.5-14B",
        "recommended_tts": "xtts",
        "quality_stars": 4,
        "speed_note": "~1.5 сек",
        "order": 6,
    },
    {
        "gpu_name": "RTX 4080",
        "gpu_vram_gb": 16,
        "gpu_family": "rtx_40xx",
        "recommended_llm": "Qwen2.5-14B-AWQ",
        "recommended_tts": "xtts",
        "quality_stars": 4,
        "speed_note": "~1 сек",
        "order": 7,
    },
    {
        "gpu_name": "RTX 4090",
        "gpu_vram_gb": 24,
        "gpu_family": "rtx_40xx",
        "recommended_llm": "Qwen2.5-32B-AWQ",
        "recommended_tts": "xtts",
        "quality_stars": 5,
        "speed_note": "~0.8 сек",
        "order": 8,
    },
]

DEFAULT_FOLLOWUP_RULES = [
    {
        "name": "GitHub без возврата (24ч)",
        "trigger": "clicked_github_no_return",
        "delay_hours": 24,
        "segment_filter": "diy",
        "message_template": (
            "👋 Привет! Как успехи с установкой AI Secretary?\n\n"
            "Если всё работает — буду рад звезде на GitHub ⭐\n\n"
            "Если застряли — напишите, помогу разобраться."
        ),
        "buttons": [
            {"text": "⭐ Всё работает!", "callback_data": "github_success"},
            {"text": "❓ Есть вопросы", "callback_data": "faq_ask"},
            {"text": "⚡ Установите за меня", "callback_data": "install_5k"},
        ],
        "max_sends": 2,
        "order": 1,
    },
    {
        "name": "Посмотрел цену (48ч)",
        "trigger": "viewed_price_no_action",
        "delay_hours": 48,
        "segment_filter": "basic",
        "message_template": (
            "👋 Вы интересовались установкой AI Secretary.\n\nМожет, остались вопросы?"
        ),
        "buttons": [
            {"text": "⚡ Хочу установить", "callback_data": "install_5k"},
            {"text": "❓ Есть вопросы", "callback_data": "faq_ask"},
            {"text": "❌ Не актуально", "callback_data": "followup_stop"},
        ],
        "max_sends": 2,
        "order": 2,
    },
    {
        "name": "Неактивный 7 дней",
        "trigger": "inactive_7_days",
        "delay_hours": 168,
        "segment_filter": None,
        "message_template": (
            "👋 Давно не виделись!\n\n"
            "Если AI Secretary всё ещё актуален — заходите, "
            "появились новые возможности."
        ),
        "buttons": [
            {"text": "📖 Что нового?", "callback_data": "changelog"},
            {"text": "🔔 Подписаться на обновления", "callback_data": "subscribe"},
            {"text": "❌ Отписаться", "callback_data": "unsubscribe"},
        ],
        "max_sends": 1,
        "order": 3,
    },
]

# ============== Claude Code Sessions ==============


class ClaudeCodeSession(Base):
    """Claude Code CLI session for web UI."""

    __tablename__ = "claude_code_sessions"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    cli_session_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(255), default="New session")
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="active"
    )  # active, completed, error, aborted
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    total_turns: Mapped[int] = mapped_column(Integer, default=0)
    max_turns: Mapped[int] = mapped_column(Integer, default=50)
    working_directory: Mapped[str] = mapped_column(String(500), default="/opt/ai-secretary")
    events_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "cli_session_id": self.cli_session_id,
            "title": self.title,
            "owner_id": self.owner_id,
            "status": self.status,
            "model": self.model,
            "total_turns": self.total_turns,
            "max_turns": self.max_turns,
            "working_directory": self.working_directory,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class ClaudeCodeProject(Base):
    """Claude Code project directory (local or SSH remote)."""

    __tablename__ = "claude_code_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    path: Mapped[str] = mapped_column(String(500))
    type: Mapped[str] = mapped_column(String(20), default="local")  # "local" or "ssh"
    ssh_host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ssh_user: Mapped[str] = mapped_column(String(100), default="root")
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    ssh_key_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    created: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "type": self.type,
            "ssh_host": self.ssh_host,
            "ssh_user": self.ssh_user,
            "ssh_port": self.ssh_port,
            "ssh_key_path": self.ssh_key_path,
            "owner_id": self.owner_id,
            "workspace_id": self.workspace_id,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class KanbanTaskStatus(str, enum.Enum):
    """Status values for kanban tasks."""

    draft = "draft"
    todo = "todo"
    in_progress = "in_progress"
    review = "review"
    done = "done"


class KanbanProject(Base):
    """Kanban project linked to a GitHub repository."""

    __tablename__ = "kanban_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    github_owner: Mapped[str] = mapped_column(String(100))
    github_repo: Mapped[str] = mapped_column(String(100))
    github_token: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    label_mapping: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    last_synced: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    created: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    tasks: Mapped[list["KanbanTask"]] = relationship(
        "KanbanTask", back_populates="project", cascade="all, delete-orphan", lazy="noload"
    )

    _DEFAULT_LABEL_MAPPING = {
        "todo": "status:todo",
        "in_progress": "status:in_progress",
        "review": "status:review",
    }

    def get_label_mapping(self) -> dict:
        if self.label_mapping:
            try:
                result: dict = json.loads(self.label_mapping)
                return result
            except (json.JSONDecodeError, TypeError):
                pass
        return dict(self._DEFAULT_LABEL_MAPPING)

    def get_reverse_label_mapping(self) -> dict:
        return {v: k for k, v in self.get_label_mapping().items()}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "github_owner": self.github_owner,
            "github_repo": self.github_repo,
            "has_token": bool(self.github_token),
            "webhook_secret_set": bool(self.webhook_secret),
            "label_mapping": self.get_label_mapping(),
            "sync_enabled": self.sync_enabled,
            "last_synced": self.last_synced.isoformat() if self.last_synced else None,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class KanbanTask(Base):
    """Kanban task card."""

    __tablename__ = "kanban_tasks"
    __table_args__ = (
        UniqueConstraint("project_id", "github_issue_number", name="uq_task_project_issue"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="draft", server_default="draft", index=True
    )
    is_private: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    assignee: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_by: Mapped[str] = mapped_column(String(100), index=True)
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    start_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    due_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    project_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("kanban_projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    github_issue_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    project: Mapped[Optional["KanbanProject"]] = relationship(
        "KanbanProject", back_populates="tasks", lazy="noload"
    )
    checklist: Mapped[list["KanbanChecklistItem"]] = relationship(
        "KanbanChecklistItem", back_populates="task", cascade="all, delete-orphan", lazy="noload"
    )
    dependencies_as_blocker: Mapped[list["KanbanTaskDependency"]] = relationship(
        "KanbanTaskDependency",
        foreign_keys="KanbanTaskDependency.blocker_id",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    dependencies_as_dependent: Mapped[list["KanbanTaskDependency"]] = relationship(
        "KanbanTaskDependency",
        foreign_keys="KanbanTaskDependency.dependent_id",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "is_private": self.is_private,
            "assignee": self.assignee,
            "created_by": self.created_by,
            "owner_id": self.owner_id,
            "start_date": self.start_date,
            "due_date": self.due_date,
            "position": self.position,
            "tags": json.loads(self.tags) if self.tags else [],
            "project_id": self.project_id,
            "github_issue_number": self.github_issue_number,
            "checklist": [c.to_dict() for c in self.checklist] if self.checklist else [],
            "blockers": [d.blocker_id for d in self.dependencies_as_dependent]
            if self.dependencies_as_dependent
            else [],
            "dependents": [d.dependent_id for d in self.dependencies_as_blocker]
            if self.dependencies_as_blocker
            else [],
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class KanbanTaskDependency(Base):
    """Dependency link between two kanban tasks (blocker blocks dependent)."""

    __tablename__ = "kanban_task_dependencies"

    blocker_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("kanban_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    dependent_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("kanban_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )


class KanbanChecklistItem(Base):
    """Checklist item inside a kanban task."""

    __tablename__ = "kanban_checklist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("kanban_tasks.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(String(500))
    is_done: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    task: Mapped["KanbanTask"] = relationship("KanbanTask", back_populates="checklist")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "text": self.text,
            "is_done": self.is_done,
            "position": self.position,
        }


DEFAULT_TESTIMONIALS = [
    {
        "text": "Поставил за вечер, работает как часы. Клонировал свой голос — клиенты не отличают от живого!",
        "author": "Дмитрий, IT-компания",
        "rating": 5,
        "order": 1,
    },
    {
        "text": "Сэкономили 180К в год на SaaS-ботах. Окупилось за первый месяц.",
        "author": "Алексей, автосалон",
        "rating": 5,
        "order": 2,
    },
    {
        "text": "Отличный проект для тех, кто ценит приватность данных. Всё на своём сервере.",
        "author": "Мария, клиника",
        "rating": 4,
        "order": 3,
    },
]
