"""Procurement models: unified product offers for the single-search pipeline.

A `ProductOffer` is one structured, real row from one source (own site,
EKF IMS, or a supplier price list). The unified search queries this table so
the assistant only ever sees real articles/prices/stock — never generated ones.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


# Source discriminators — one adapter populates each.
SOURCE_SITE = "site"  # own WooCommerce catalog (stalkerelectric.kz)
SOURCE_EKF = "ekf"  # EKF IMS partner API
SOURCE_SUPPLIER = "supplier"  # parsed supplier xlsx/csv price lists


class ProductOffer(Base):
    """One real offer (position + price + stock) from one source.

    Uniqueness is (source, source_key) so re-syncing a source upserts rather
    than duplicates. `source_key` is the source's own id (WooCommerce product
    id, EKF article, or supplier-file row key).
    """

    __tablename__ = "product_offers"
    __table_args__ = (UniqueConstraint("source", "source_key", name="uq_offer_source_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    source: Mapped[str] = mapped_column(String(20), index=True)
    source_key: Mapped[str] = mapped_column(String(200))
    supplier_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    article: Mapped[Optional[str]] = mapped_column(String(200), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(500), index=True)
    brand: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="KZT")
    in_stock: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    stock_qty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lead_time_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    extra: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON blob, raw source

    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id"), default=1)
    updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "source_key": self.source_key,
            "supplier_name": self.supplier_name,
            "article": self.article,
            "name": self.name,
            "brand": self.brand,
            "category": self.category,
            "price": self.price,
            "currency": self.currency,
            "in_stock": self.in_stock,
            "stock_qty": self.stock_qty,
            "lead_time_days": self.lead_time_days,
            "url": self.url,
            "updated": self.updated.isoformat() if self.updated else None,
        }
