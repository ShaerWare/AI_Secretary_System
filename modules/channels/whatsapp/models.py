"""WhatsApp channel models."""

import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


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

    # Transport: "cloud" = Meta Cloud API, "bridge" = self-hosted provider
    # (services/whatsapp-bridge, a phone linked by QR over multi-device)
    provider: Mapped[str] = mapped_column(String(20), default="cloud", server_default="cloud")
    # Bridge location + shared secret. Both fall back to the bot's environment
    # (WHATSAPP_BRIDGE_URL / WHATSAPP_BRIDGE_TOKEN) when left empty, so the
    # secret doesn't have to be duplicated per instance.
    bridge_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    bridge_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

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
            # Transport
            "provider": self.provider or "cloud",
            "bridge_url": self.bridge_url,
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
        if include_token:
            if self.access_token:
                result["access_token"] = self.access_token
                result["app_secret"] = self.app_secret
            if self.bridge_token:
                result["bridge_token"] = self.bridge_token
        return result
