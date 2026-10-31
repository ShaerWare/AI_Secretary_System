"""Client card: what the assistant remembers about a client between dialogues.

One row per (workspace, channel, client address). The address is the chat
session's ``source_id`` (``"<instance>:<phone>"`` for WhatsApp), not the session
id: the bot keeps the phone → session mapping in process memory only, so every
bot restart opens a fresh, empty session for the same person. The card is what
survives that.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


def _iso(value: Optional[datetime]) -> Optional[str]:
    """Naive UTC → ISO with an explicit zone, so the browser doesn't read it as local."""
    return value.isoformat() + "Z" if value else None


class ClientProfile(Base):
    __tablename__ = "client_profiles"
    __table_args__ = (
        UniqueConstraint("workspace_id", "channel", "external_id", name="uq_client_profile"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(Integer, default=1, index=True)
    channel: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str] = mapped_column(String(150), index=True)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    # Written by the LLM after each dialogue; a manager may edit it.
    card_md: Mapped[str] = mapped_column(Text, default="")
    # Written only by people — the LLM never sees it as something to rewrite.
    manager_notes: Mapped[str] = mapped_column(Text, default="")
    # Newest message already folded into the card: the next pass reads only
    # what came after it.
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_session_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sessions: Mapped[list] = mapped_column(JSON, default=list)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "channel": self.channel,
            "external_id": self.external_id,
            "display_name": self.display_name,
            "card_md": self.card_md,
            "manager_notes": self.manager_notes,
            "last_message_at": _iso(self.last_message_at),
            "last_session_id": self.last_session_id,
            "sessions": list(self.sessions or []),
            "created": _iso(self.created),
            "updated": _iso(self.updated),
        }
