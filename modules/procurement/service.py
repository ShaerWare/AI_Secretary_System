"""Procurement service: upsert offers per source + unified deterministic search.

This is the code-pipeline core of the "single search" feature. Adapters
(site / EKF / supplier) upsert real rows here; `search()` ranks them. The LLM
never invents data — it only reformulates rows this search returns.
"""

import json
import logging
import re
from typing import List, Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy import select as sa_select

from db.database import AsyncSessionLocal
from db.retry import retry_on_busy
from modules.procurement.models import ProductOffer


logger = logging.getLogger(__name__)

# Ranking preference between sources when the same position appears in several.
# Own stock first, then EKF (direct API), then generic supplier price lists.
SOURCE_PRIORITY = {"site": 0, "ekf": 1, "supplier": 2}

_TOKEN_RE = re.compile(r"[^\w]+", re.UNICODE)


def _norm(s: Optional[str]) -> str:
    """Lowercase + strip punctuation/space, Unicode-aware (handles Cyrillic)."""
    if not s:
        return ""
    return _TOKEN_RE.sub("", s.lower())


def _tokens(s: str) -> List[str]:
    return [t for t in _TOKEN_RE.split(s.lower()) if t]


class OfferService:
    """CRUD + search over `product_offers`."""

    @retry_on_busy()
    async def replace_source_offers(
        self, source: str, offers: List[dict], workspace_id: int = 1
    ) -> int:
        """Full re-sync of one source: delete its offers, insert the fresh set.

        `offers` is a list of dicts with keys matching ProductOffer fields
        (must include source_key + name). Returns number of rows written.
        """
        async with AsyncSessionLocal() as session:
            await session.execute(
                sa_delete(ProductOffer).where(
                    ProductOffer.source == source,
                    ProductOffer.workspace_id == workspace_id,
                )
            )
            rows = 0
            for o in offers:
                if not o.get("source_key") or not o.get("name"):
                    continue
                extra = o.get("extra")
                session.add(
                    ProductOffer(
                        source=source,
                        source_key=str(o["source_key"]),
                        supplier_name=o.get("supplier_name"),
                        article=o.get("article"),
                        name=o["name"][:500],
                        brand=o.get("brand"),
                        category=o.get("category"),
                        price=o.get("price"),
                        currency=o.get("currency", "KZT"),
                        in_stock=o.get("in_stock"),
                        stock_qty=o.get("stock_qty"),
                        lead_time_days=o.get("lead_time_days"),
                        url=o.get("url"),
                        extra=json.dumps(extra, ensure_ascii=False) if extra else None,
                        workspace_id=workspace_id,
                    )
                )
                rows += 1
            await session.commit()
            logger.info("procurement: replaced %d offers for source=%s", rows, source)
            return rows

    async def count(self, source: Optional[str] = None, workspace_id: int = 1) -> int:
        async with AsyncSessionLocal() as session:
            stmt = sa_select(ProductOffer).where(ProductOffer.workspace_id == workspace_id)
            if source:
                stmt = stmt.where(ProductOffer.source == source)
            res = await session.execute(stmt)
            return len(res.scalars().all())

    async def search(
        self,
        query: str,
        limit: int = 10,
        in_stock_only: bool = False,
        workspace_id: int = 1,
    ) -> List[dict]:
        """Rank real offers against a free-text position query.

        Ranking (lower is better): exact article > article contains query >
        name contains all tokens > name contains any token. Ties broken by
        in-stock, source priority, then price. Returns [] if nothing matches
        (the caller must then say "не найдено" — never invent a position).
        """
        q_norm = _norm(query)
        q_tokens = _tokens(query)
        if not q_norm and not q_tokens:
            return []

        async with AsyncSessionLocal() as session:
            stmt = sa_select(ProductOffer).where(ProductOffer.workspace_id == workspace_id)
            if in_stock_only:
                stmt = stmt.where(ProductOffer.in_stock.is_(True))
            res = await session.execute(stmt)
            rows = res.scalars().all()

        scored = []
        for r in rows:
            art_norm = _norm(r.article)
            name_low = (r.name or "").lower()
            rank = None
            if q_norm and art_norm and art_norm == q_norm:
                rank = 0
            elif q_norm and art_norm and q_norm in art_norm:
                rank = 1
            elif q_tokens and all(t in name_low for t in q_tokens):
                rank = 2
            elif q_tokens and any(t in name_low for t in q_tokens):
                rank = 3
            if rank is None:
                continue
            scored.append((rank, r))

        scored.sort(
            key=lambda pair: (
                pair[0],
                0 if pair[1].in_stock else 1,
                SOURCE_PRIORITY.get(pair[1].source, 9),
                pair[1].price if pair[1].price is not None else float("inf"),
            )
        )
        out = []
        for rank, r in scored[:limit]:
            d = r.to_dict()
            d["match"] = ["article_exact", "article_partial", "name_all", "name_any"][rank]
            out.append(d)
        return out


offer_service = OfferService()
