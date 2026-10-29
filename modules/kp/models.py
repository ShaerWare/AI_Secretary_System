"""КП (commercial offers) kept in the PIM, mirrored here for approval and timers.

The PIM (ar-gs.ru) owns the document itself — number, PDF, client link. This
side owns what the PIM does not do: who approved it, how it reaches the client,
and what happens while the client is silent or after the offer expires.
"""

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


# Local workflow statuses. PIM statuses (draft/sent/viewed/clarification/
# accepted) are kept separately in ``pim_status``.
STATUS_PENDING = "pending"  # draft in the PIM, waiting for a manager/director
STATUS_SENDING = "sending"
STATUS_SENT = "sent"
STATUS_VIEWED = "viewed"
STATUS_CLARIFICATION = "clarification"
STATUS_ACCEPTED = "accepted"
STATUS_EXPIRED = "expired"
STATUS_LOST = "lost"
STATUS_REJECTED = "rejected"  # declined before it ever reached the client
STATUS_SUPERSEDED = "superseded"  # replaced by a reissued quote
STATUS_FAILED = "failed"  # approval went through, delivery did not

STATUSES = (
    STATUS_PENDING,
    STATUS_SENDING,
    STATUS_SENT,
    STATUS_VIEWED,
    STATUS_CLARIFICATION,
    STATUS_ACCEPTED,
    STATUS_EXPIRED,
    STATUS_LOST,
    STATUS_REJECTED,
    STATUS_SUPERSEDED,
    STATUS_FAILED,
)
# The client has the offer and has not decided yet — timers run on these.
OPEN_STATUSES = (STATUS_SENT, STATUS_VIEWED, STATUS_CLARIFICATION)
# Nothing more will happen to these.
CLOSED_STATUSES = (STATUS_ACCEPTED, STATUS_LOST, STATUS_REJECTED, STATUS_SUPERSEDED)

DELIVERY_WHATSAPP = "whatsapp"
DELIVERY_EMAIL = "email"
DELIVERY_LINK = "link"  # manager sends the link by other means
DELIVERY_MODES = (DELIVERY_WHATSAPP, DELIVERY_EMAIL, DELIVERY_LINK)

ORIGIN_ASSISTANT = "assistant"
ORIGIN_MANUAL = "manual"  # created from the admin panel
ORIGIN_PIM = "pim"  # created by a manager directly in the PIM, imported


def _iso(value: Optional[datetime]) -> Optional[str]:
    """Naive UTC → ISO with an explicit zone, so the browser doesn't read it as local."""
    return value.isoformat() + "Z" if value else None


class KpQuote(Base):
    __tablename__ = "kp_quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pim_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, unique=True)
    number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=STATUS_PENDING, index=True)
    pim_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    origin: Mapped[str] = mapped_column(String(20), default=ORIGIN_MANUAL)

    customer: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # Positions the assistant could not price — for the manager, never quoted.
    flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    valid_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    valid_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    request_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    link: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    link_active: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    edit_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    delivery: Mapped[str] = mapped_column(String(20), default=DELIVERY_LINK)
    channel_instance_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    target: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    outbound_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reissued_from: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reissued_to: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    decided_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pim_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    viewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pim_id": self.pim_id,
            "number": self.number,
            "status": self.status,
            "pim_status": self.pim_status,
            "origin": self.origin,
            "customer": self.customer or {},
            "items": self.items or [],
            "flags": self.flags or [],
            "total": self.total,
            "currency": self.currency,
            "valid_days": self.valid_days,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "request_number": self.request_number,
            "link": self.link,
            "link_active": self.link_active,
            "edit_url": self.edit_url,
            "delivery": self.delivery,
            "channel_instance_id": self.channel_instance_id,
            "target": self.target,
            "email": self.email,
            "message": self.message,
            "session_id": self.session_id,
            "outbound_message_id": self.outbound_message_id,
            "reissued_from": self.reissued_from,
            "reissued_to": self.reissued_to,
            "note": self.note,
            "error": self.error,
            "created_by": self.created_by,
            "decided_by": self.decided_by,
            "pim_created_at": _iso(self.pim_created_at),
            "created": _iso(self.created),
            "updated": _iso(self.updated),
            "decided_at": _iso(self.decided_at),
            "sent_at": _iso(self.sent_at),
            "viewed_at": _iso(self.viewed_at),
            "closed_at": _iso(self.closed_at),
        }


# Timer triggers: what moment ``offset_hours`` is counted from.
TRIGGER_NOT_APPROVED = "not_approved"  # draft waits for approval, from creation
TRIGGER_NOT_VIEWED = "not_viewed"  # sent, client hasn't opened it, from sending
TRIGGER_VIEWED_NO_REPLY = "viewed_no_reply"  # opened, no decision, from opening
TRIGGER_BEFORE_EXPIRY = "before_expiry"  # N hours before the end of validity
TRIGGER_EXPIRED = "expired"  # N hours after the end of validity
TRIGGERS = (
    TRIGGER_NOT_APPROVED,
    TRIGGER_NOT_VIEWED,
    TRIGGER_VIEWED_NO_REPLY,
    TRIGGER_BEFORE_EXPIRY,
    TRIGGER_EXPIRED,
)

ACTION_NOTIFY = "notify"  # tell the manager (panel + Telegram)
ACTION_CLIENT_MESSAGE = "client_message"  # queue a message to the client for approval
ACTION_MARK_LOST = "mark_lost"
ACTIONS = (ACTION_NOTIFY, ACTION_CLIENT_MESSAGE, ACTION_MARK_LOST)


class KpTimerRule(Base):
    __tablename__ = "kp_timer_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    trigger: Mapped[str] = mapped_column(String(30))
    offset_hours: Mapped[float] = mapped_column(Float, default=0)
    action: Mapped[str] = mapped_column(String(30))
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "trigger": self.trigger,
            "offset_hours": self.offset_hours,
            "action": self.action,
            "message": self.message,
            "enabled": self.enabled,
            "sort": self.sort,
            "created": _iso(self.created),
            "updated": _iso(self.updated),
        }


class KpEvent(Base):
    """Something that happened to a quote: a fired timer, a status change.

    ``dedup_key`` makes every timer fire once per quote and validity period.
    Events of kind ``notify`` are the manager's to-do list until acknowledged.
    """

    __tablename__ = "kp_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quote_id: Mapped[int] = mapped_column(Integer, index=True)
    rule_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    dedup_key: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))
    text: Mapped[str] = mapped_column(Text)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (Index("ix_kp_events_dedup", "quote_id", "dedup_key"),)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "quote_id": self.quote_id,
            "rule_id": self.rule_id,
            "kind": self.kind,
            "text": self.text,
            "created": _iso(self.created),
            "acknowledged_by": self.acknowledged_by,
            "acknowledged_at": _iso(self.acknowledged_at),
        }
