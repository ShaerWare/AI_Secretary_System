"""Outbound approval queue: assistant replies waiting for a human decision."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


STATUS_PENDING = "pending"
STATUS_SENT = "sent"
STATUS_REJECTED = "rejected"
STATUS_FAILED = "failed"
STATUSES = (STATUS_PENDING, STATUS_SENT, STATUS_REJECTED, STATUS_FAILED)


def _iso(value: Optional[datetime]) -> Optional[str]:
    """Naive UTC → ISO with an explicit zone, so the browser doesn't read it as local."""
    return value.isoformat() + "Z" if value else None


class OutboundMessage(Base):
    """One assistant reply held back from the client until someone approves it.

    ``draft_text`` is what the assistant wrote and never changes; ``text`` is
    what will go (or went) to the client, so an edit stays visible next to the
    original.
    """

    __tablename__ = "outbound_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(20), index=True)  # whatsapp
    instance_id: Mapped[str] = mapped_column(String(50), index=True)
    target: Mapped[str] = mapped_column(String(100))  # phone / @lid address
    session_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    # Assistant message in chat_messages carrying this reply, so an edit or a
    # rejection keeps the dialogue history equal to what the client really saw.
    chat_message_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    client_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    draft_text: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=STATUS_PENDING, index=True)
    ack_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    decided_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (Index("ix_outbound_target_status", "channel", "target", "status"),)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "channel": self.channel,
            "instance_id": self.instance_id,
            "target": self.target,
            "session_id": self.session_id,
            "client_text": self.client_text,
            "draft_text": self.draft_text,
            "text": self.text,
            "edited": self.text != self.draft_text,
            "status": self.status,
            "ack_sent": self.ack_sent,
            "error": self.error,
            "created": _iso(self.created),
            "updated": _iso(self.updated),
            "decided_by": self.decided_by,
            "decided_at": _iso(self.decided_at),
            "sent_at": _iso(self.sent_at),
        }
