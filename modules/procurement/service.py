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

# Conversational filler dropped from queries so it doesn't match everything
# (e.g. "и" is a substring of most Russian words). Real product tokens stay.
_STOPWORDS = {
    "и",
    "в",
    "на",
    "с",
    "по",
    "для",
    "или",
    "что",
    "это",
    "есть",
    "нет",
    "нужен",
    "нужна",
    "нужно",
    "нужны",
    "надо",
    "хочу",
    "дай",
    "дайте",
    "какой",
    "какая",
    "какие",
    "почём",
    "почем",
    "цена",
    "цены",
    "сколько",
    "стоит",
    "стоят",
    "а",
    "у",
    "от",
    "до",
    "к",
    "же",
    "ли",
    "бы",
    "мне",
    "подбери",
    "подберите",
    "покажи",
    "найди",
    "ищу",
    "the",
    "and",
    "for",
    # request meta-words (email subjects), not product terms
    "запрос",
    "запроса",
    "стоимость",
    "стоимости",
    "цену",
    "прайс",
    "коммерческое",
    "кп",
    "счёт",
    "счет",
    "купить",
    "заказать",
    "заявка",
    "поставка",
    "поставку",
    "сообщение",
    "форма",
    "формы",
}


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
        self,
        source: str,
        offers: List[dict],
        workspace_id: int = 1,
        scope_key: Optional[str] = None,
    ) -> int:
        """Full re-sync of one source: delete its offers, insert the fresh set.

        `offers` is a list of dicts with keys matching ProductOffer fields
        (must include source_key + name). When `scope_key` is given, only rows
        whose ``source_key`` starts with ``{scope_key}#`` are replaced — so
        several suppliers can share source='supplier' without wiping each other,
        and renaming a supplier doesn't orphan its rows. Returns rows written.
        """
        async with AsyncSessionLocal() as session:
            del_stmt = sa_delete(ProductOffer).where(
                ProductOffer.source == source,
                ProductOffer.workspace_id == workspace_id,
            )
            if scope_key is not None:
                del_stmt = del_stmt.where(ProductOffer.source_key.like(f"{scope_key}#%"))
            await session.execute(del_stmt)
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
        name match (more matched query tokens = better). Stopwords/1-char tokens
        are dropped so filler like "и"/"что" doesn't match everything. Ties
        broken by in-stock, source priority, then price. Returns [] if nothing
        matches (caller must then say "не найдено" — never invent a position).
        """
        q_norm = _norm(query)
        q_tokens = [t for t in _tokens(query) if len(t) >= 2 and t not in _STOPWORDS]
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
            # include category so items with terse names (1C exports) stay findable
            name_low = (r.name or "").lower()
            if r.category:
                name_low = f"{name_low} {r.category.lower()}"
            if q_norm and art_norm and art_norm == q_norm:
                primary, misses = 0, 0
            elif len(q_norm) >= 4 and art_norm and q_norm in art_norm:
                primary, misses = 1, 0
            elif q_tokens:
                matched = sum(1 for t in q_tokens if t in name_low)
                if not matched:
                    continue
                primary, misses = 2, len(q_tokens) - matched
            else:
                continue
            # significant matches: tokens len≥4 (short/stray ones like «из», com,
            # at don't count) — computed here where name_low is the current row.
            sig_matched = sum(1 for t in q_tokens if len(t) >= 4 and t in name_low)
            scored.append((primary, misses, sig_matched, r))

        scored.sort(
            key=lambda x: (
                x[0],
                x[1],
                0 if x[3].in_stock else 1,
                SOURCE_PRIORITY.get(x[3].source, 9),
                x[3].price if x[3].price is not None else float("inf"),
            )
        )
        labels = {0: "article_exact", 1: "article_partial", 2: "name"}
        out = []
        for primary, misses, sig_matched, r in scored[:limit]:
            d = r.to_dict()
            d["match"] = labels[primary]
            d["matched_tokens"] = (len(q_tokens) - misses) if primary == 2 else len(q_tokens)
            # confident = exact/partial article OR ≥2 significant name tokens —
            # spam subjects with a couple of incidental short hits aren't "ready".
            d["confident"] = primary in (0, 1) or sig_matched >= 2
            out.append(d)
        return out


offer_service = OfferService()
