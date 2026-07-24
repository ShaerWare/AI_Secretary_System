"""Pricing engine: supplier offer -> purchase price + client (КП) price.

Rules from the client's Reestr v3 (sheet "2. Ценообразование"), keyed by
supplier config in ``suppliers/registry.py``:

- KZT dealer suppliers (SunWell/EKF, X-Trade, ЭКТ): client = raw × (1+markup);
  prices already include VAT. purchase = raw × (1−discount) (discount 0 → raw).
- Chint (РРЦ via Аксима): client = РРЦ (raw); purchase = РРЦ × 0.70.
- Аксима: client = max(РРЦ from Chint file, raw × 1.30); purchase = raw.
- Мегазаказ (USD, no VAT): purchase = $×rate×0.72; client = $×rate×1.20×1.16.
- Промситех: no markup (client = raw). (file not provided yet)

Rule 16: if purchase ≥ client (zero/negative margin) → flag for the director,
do not auto-quote. Rule 10/18: VAT 16%; Аксима/Промситех already include it —
never add twice (``vat_included``).
"""

import logging
from typing import Optional

from sqlalchemy import select as sa_select

from db.database import AsyncSessionLocal
from modules.procurement.models import ProductOffer
from modules.procurement.rate_service import get_usd_kzt
from modules.procurement.suppliers.registry import get_supplier


logger = logging.getLogger(__name__)

VAT_MULT = 1.16


def supplier_key(source_key: Optional[str]) -> Optional[str]:
    """'sunwell#123' -> 'sunwell'."""
    return source_key.split("#", 1)[0] if source_key else None


def compute_pricing(offer: dict, rate: Optional[float] = None, rrc: Optional[float] = None) -> dict:
    """Pure math: offer + USD rate (if needed) + Аксима РРЦ -> pricing dict.

    Returns {ok, client_price, purchase_price, currency, ...} or {ok: False,
    reason} when it can't price (non-supplier / unknown supplier / missing rate).
    """
    if offer.get("source") != "supplier":
        return {"ok": False, "reason": "not_supplier"}  # site offers are already retail
    key = supplier_key(offer.get("source_key"))
    cfg = get_supplier(key)
    raw = offer.get("price")
    if not cfg or raw is None:
        return {"ok": False, "reason": "no_config_or_price"}

    markup = 1 + (cfg.get("markup_pct") or 0) / 100
    disc = 1 - (cfg.get("purchase_discount_pct") or 0) / 100
    src_cur = cfg.get("currency", "KZT")

    if src_cur == "USD":
        if not rate:
            return {"ok": False, "reason": "no_rate", "source_currency": "USD"}
        base = raw * rate
        purchase = base * disc
        client = base * markup
        if not cfg.get("vat_included"):
            client *= VAT_MULT
    else:
        purchase = raw * disc
        client = raw * markup
        if not cfg.get("vat_included"):
            client *= VAT_MULT

    # Аксима: КП = max(РРЦ из файла Chint, закупка × 1.30)
    if key == "aksima" and rrc:
        client = max(rrc, client)

    purchase = round(purchase, 2)
    client = round(client, 2)
    return {
        "ok": True,
        "client_price": client,
        "purchase_price": purchase,
        "currency": "KZT",
        "source_currency": src_cur,
        "rate": rate if src_cur == "USD" else None,
        "markup_pct": cfg.get("markup_pct"),
        "supplier": cfg.get("name"),
        # rule 16: zero/negative margin — don't auto-quote, show director
        "zero_margin_flag": purchase >= client,
    }


async def _lookup_rrc(article: str, workspace_id: int = 1) -> Optional[float]:
    """РРЦ price for an article from the Chint (via Аксима) offers."""
    if not article:
        return None
    async with AsyncSessionLocal() as session:
        stmt = (
            sa_select(ProductOffer.price)
            .where(
                ProductOffer.source_key.like("aksima_chint_rrc#%"),
                ProductOffer.article == article,
                ProductOffer.workspace_id == workspace_id,
            )
            .limit(1)
        )
        return (await session.execute(stmt)).scalar()


async def price_offer(offer: dict, rate_info: Optional[dict] = None) -> dict:
    """Full pricing for one supplier offer: resolves USD rate + Аксима РРЦ.

    `rate_info` (from get_usd_kzt) can be passed to avoid re-fetching per offer.
    Adds `rate_date`/`rate_source`/`rate_stale` when a USD rate was used.
    """
    key = supplier_key(offer.get("source_key"))
    cfg = get_supplier(key)
    rate = None
    ri = None
    if cfg and cfg.get("currency") == "USD":
        ri = rate_info or await get_usd_kzt()
        rate = ri.get("rate")
    rrc = await _lookup_rrc(offer["article"]) if key == "aksima" and offer.get("article") else None

    result = compute_pricing(offer, rate=rate, rrc=rrc)
    if ri and result.get("ok"):
        result["rate_date"] = ri.get("date")
        result["rate_source"] = ri.get("source")
        result["rate_stale"] = ri.get("stale")
    return result
