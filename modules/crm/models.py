"""CRM models: amoCRM config and sync log."""

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
)
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


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
