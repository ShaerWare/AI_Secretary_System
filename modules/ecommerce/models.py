"""Ecommerce models: WooCommerce config."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


class WooCommerceConfig(Base):
    """WooCommerce store connection config (singleton, id=1)."""

    __tablename__ = "woocommerce_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_url: Mapped[str] = mapped_column(String(500), default="")
    consumer_key: Mapped[str] = mapped_column(String(500), default="")
    consumer_secret: Mapped[str] = mapped_column(String(500), default="")
    is_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    products_count: Mapped[int] = mapped_column(Integer, default=0)
    categories_count: Mapped[int] = mapped_column(Integer, default=0)
    orders_count: Mapped[int] = mapped_column(Integer, default=0)
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id"), default=1)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def to_dict(self, include_secrets: bool = False) -> dict:
        result: dict = {
            "id": self.id,
            "store_url": self.store_url,
            "is_connected": self.is_connected,
            "sync_enabled": self.sync_enabled,
            "last_sync_at": self.last_sync_at,
            "products_count": self.products_count,
            "categories_count": self.categories_count,
            "orders_count": self.orders_count,
            "workspace_id": self.workspace_id,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }
        if include_secrets:
            result["consumer_key"] = self.consumer_key
            result["consumer_secret"] = self.consumer_secret
        else:
            result["consumer_key_masked"] = (
                "***" + self.consumer_key[-4:]
                if self.consumer_key and len(self.consumer_key) > 4
                else ""
            )
            result["consumer_secret_masked"] = (
                "***" + self.consumer_secret[-4:]
                if self.consumer_secret and len(self.consumer_secret) > 4
                else ""
            )
        return result
