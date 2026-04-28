"""Monitoring models: audit log, usage tracking, limits."""

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


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
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # Usage metrics (tokens for LLM, characters for TTS, seconds for STT)
    units_consumed: Mapped[int] = mapped_column(Integer, default=1)
    cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Additional details
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    # Indexes for common queries
    __table_args__ = (
        Index("ix_usage_log_service_timestamp", "service_type", "timestamp"),
        Index("ix_usage_log_source_timestamp", "source", "timestamp"),
        Index("ix_usage_log_user_timestamp", "user_id", "timestamp"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "service_type": self.service_type,
            "action": self.action,
            "source": self.source,
            "source_id": self.source_id,
            "user_id": self.user_id,
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
    )  # "tts", "stt", "llm"
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
