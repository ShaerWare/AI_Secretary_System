"""Google OAuth token storage model."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


class GoogleOAuthToken(Base):
    __tablename__ = "google_oauth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    scopes: Mapped[str] = mapped_column(Text, nullable=False)  # space-separated
    google_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "google_email": self.google_email,
            "scopes": self.scopes.split() if self.scopes else [],
            "token_expiry": self.token_expiry.isoformat() if self.token_expiry else None,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }
