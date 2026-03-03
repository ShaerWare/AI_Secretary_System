"""Telephony models: GSM call and SMS logs."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


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
