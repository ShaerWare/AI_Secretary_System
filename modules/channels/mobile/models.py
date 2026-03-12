"""Mobile app channel models."""

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


class MobileAppInstance(Base):
    """Mobile app instance with individual configuration.

    Each instance represents a pre-configured assistant that users
    can be assigned to via ResourceShare.
    """

    __tablename__ = "mobile_app_instances"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )

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

    def get_knowledge_collection_ids(self) -> List[int]:
        if not self.knowledge_collection_ids:
            return []
        try:
            result: List[int] = json.loads(self.knowledge_collection_ids)
            return result
        except (json.JSONDecodeError, TypeError):
            return []

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "owner_id": self.owner_id,
            "workspace_id": self.workspace_id,
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
            "knowledge_collection_ids": self.get_knowledge_collection_ids(),
            # Rate limiting
            "rate_limit_count": self.rate_limit_count,
            "rate_limit_hours": self.rate_limit_hours,
            # Timestamps
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }
