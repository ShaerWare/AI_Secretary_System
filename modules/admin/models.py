"""Admin models: user consent."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


class UserConsent(Base):
    """User consent records for GDPR/legal compliance."""

    __tablename__ = "user_consents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(100), index=True)  # telegram_id, session_id, etc.
    user_type: Mapped[str] = mapped_column(String(20))  # "telegram", "widget", "admin"
    consent_type: Mapped[str] = mapped_column(
        String(50), index=True
    )  # "privacy_policy", "voice_recording", "data_processing", "call_recording"
    consent_version: Mapped[str] = mapped_column(String(20), default="1.0")
    granted: Mapped[bool] = mapped_column(Boolean, default=False)
    granted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)  # IPv6 max length
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Unique constraint on user_id + consent_type
    __table_args__ = (Index("ix_user_consents_user_type", "user_id", "consent_type", unique=True),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_type": self.user_type,
            "consent_type": self.consent_type,
            "consent_version": self.consent_version,
            "granted": self.granted,
            "granted_at": self.granted_at.isoformat() if self.granted_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "ip_address": self.ip_address,
            "created": self.created.isoformat() if self.created else None,
        }


# Consent types enum-like constants
CONSENT_TYPES = {
    "privacy_policy": {
        "name": "Политика конфиденциальности",
        "name_en": "Privacy Policy",
        "required": True,
        "description": "Согласие на обработку персональных данных",
    },
    "voice_recording": {
        "name": "Запись голоса",
        "name_en": "Voice Recording",
        "required": False,
        "description": "Согласие на запись и обработку голоса для TTS/STT",
    },
    "call_recording": {
        "name": "Запись звонков",
        "name_en": "Call Recording",
        "required": False,
        "description": "Согласие на запись телефонных разговоров",
    },
    "data_processing": {
        "name": "Обработка данных",
        "name_en": "Data Processing",
        "required": True,
        "description": "Согласие на обработку данных для работы сервиса",
    },
    "marketing": {
        "name": "Маркетинговые коммуникации",
        "name_en": "Marketing Communications",
        "required": False,
        "description": "Согласие на получение рекламных материалов",
    },
}
