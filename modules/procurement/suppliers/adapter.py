"""Supplier adapter: parsed price rows -> ProductOffer (source='supplier').

Stores the RAW source price + currency (dealer/purchase price — sensitive,
manager-only). The pricing engine (later) computes client price via markup +
VAT + USD rate; it is NOT stored here.
"""

import logging
from typing import List

from modules.procurement.models import SOURCE_SUPPLIER
from modules.procurement.service import offer_service
from modules.procurement.suppliers.parser import parse_supplier_file
from modules.procurement.suppliers.registry import SUPPLIERS, get_supplier


logger = logging.getLogger(__name__)


def _row_to_offer(row: dict, cfg: dict, idx: int) -> dict:
    # source_key must be unique within source='supplier' (articles are not —
    # they repeat within a file and collide across suppliers). Full re-sync per
    # supplier makes an index-based key stable enough. Article stays searchable.
    key = f"{cfg['key']}#{idx}"
    return {
        "source_key": key,
        "supplier_name": cfg["name"],
        "article": row.get("article"),
        "name": row.get("name") or "Без названия",
        "brand": cfg.get("brand"),
        "category": row.get("category"),
        "price": row.get("price"),
        "currency": cfg.get("currency", "KZT"),
        "in_stock": (row.get("stock") or 0) > 0 if "stock" in row else None,
        "stock_qty": row.get("stock"),
        "extra": {"markup_pct": cfg.get("markup_pct"), "vat_included": cfg.get("vat_included")},
    }


async def sync_supplier(key: str, workspace_id: int = 1) -> dict:
    """Parse one supplier's file(s) and rebuild its offers."""
    cfg = get_supplier(key)
    if not cfg:
        raise ValueError(f"unknown supplier: {key}")
    rows = parse_supplier_file(cfg)
    offers = [_row_to_offer(r, cfg, i) for i, r in enumerate(rows) if r.get("name")]
    written = await offer_service.replace_source_offers(
        SOURCE_SUPPLIER, offers, workspace_id=workspace_id, scope_key=cfg["key"]
    )
    logger.info("supplier %s: %d rows -> %d offers", key, len(rows), written)
    return {"supplier": cfg["name"], "rows": len(rows), "offers": written}


async def sync_all_suppliers(workspace_id: int = 1) -> List[dict]:
    """Parse every configured supplier. Skips (logs) any that fail."""
    stats = []
    for cfg in SUPPLIERS:
        try:
            stats.append(await sync_supplier(cfg["key"], workspace_id=workspace_id))
        except Exception as e:
            logger.warning("supplier %s sync failed: %s", cfg["key"], e)
            stats.append({"supplier": cfg["name"], "error": str(e)})
    return stats
