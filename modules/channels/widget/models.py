"""Widget channel models."""

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
