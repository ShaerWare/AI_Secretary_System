"""Sales models: payment log."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


class PaymentLog(Base):
    """Payment transaction log for Telegram bot payments."""

    __tablename__ = "payment_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    payment_type: Mapped[str] = mapped_column(String(20))  # "yookassa" | "stars"
    product_id: Mapped[str] = mapped_column(String(100))
    amount: Mapped[int] = mapped_column(Integer)  # kopecks for RUB, stars for XTR
    currency: Mapped[str] = mapped_column(String(10))  # "RUB" | "XTR"
    telegram_payment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    provider_payment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="completed")
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "user_id": self.user_id,
            "username": self.username,
            "payment_type": self.payment_type,
            "product_id": self.product_id,
            "amount": self.amount,
            "currency": self.currency,
            "telegram_payment_id": self.telegram_payment_id,
            "provider_payment_id": self.provider_payment_id,
            "status": self.status,
            "created": self.created.isoformat() if self.created else None,
        }
