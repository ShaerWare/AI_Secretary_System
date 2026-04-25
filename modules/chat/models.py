"""Chat models: sessions, messages, sharing."""

import json
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base


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
    web_search_enabled: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True, default=False
    )

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
            "web_search_enabled": bool(self.web_search_enabled),
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
            "web_search_enabled": bool(self.web_search_enabled),
            "amocrm_lead_id": self.amocrm_lead_id,
            "amocrm_contact_id": self.amocrm_contact_id,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }


class ChatSessionPrompt(Base):
    """Named system prompt belonging to a chat session.

    Multiple prompts per session, exactly one is_active. The active prompt's
    content is mirrored into ChatSession.system_prompt so the existing
    streaming pipeline picks it up without changes — switching prompt
    therefore changes the assistant's role while preserving conversation
    history.
    """

    __tablename__ = "chat_session_prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    content: Mapped[str] = mapped_column(Text, default="", server_default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_chat_session_prompts_session_active", "session_id", "is_active"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "name": self.name,
            "content": self.content or "",
            "is_active": bool(self.is_active),
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

    # JSON metadata (images, etc.)
    extra_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Branching fields
    parent_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("chat_messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    branch_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

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
        result = {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "edited": self.edited,
            "timestamp": self.created.isoformat() if self.created else None,
            "parent_id": self.parent_id,
            "is_active": self.is_active,
            "branch_name": self.branch_name,
        }
        if self.extra_data:
            try:
                result["metadata"] = json.loads(self.extra_data)
            except (json.JSONDecodeError, TypeError):
                pass
        return result


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
    is_default_mobile: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

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
            "is_default_mobile": self.is_default_mobile,
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
