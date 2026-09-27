"""Site adapter: WooCommerce catalog -> structured ProductOffer rows.

The first of three unified-search sources. Reuses the existing WooCommerce
client + stored credentials, so no new access is needed. EKF and supplier
adapters plug into the same `offer_service.replace_source_offers` interface.
"""

import json
import logging
from typing import Any, Optional

from app.services.woocommerce_service import get_all_products
from modules.ecommerce.service import woocommerce_service
from modules.procurement.models import SOURCE_SITE
from modules.procurement.service import offer_service


logger = logging.getLogger(__name__)

SITE_SUPPLIER_NAME = "Сайт StalkerElectric"

# Product attribute names that carry the manufacturer/brand.
_BRAND_ATTRS = {"бренд", "производитель", "brand", "manufacturer", "марка"}


def _parse_price(product: dict) -> Optional[float]:
    for key in ("price", "sale_price", "regular_price"):
        raw = product.get(key)
        if raw in (None, ""):
            continue
        try:
            return float(str(raw).replace(",", ".").replace(" ", ""))
        except (TypeError, ValueError):
            continue
    return None


def _brand(product: dict) -> Optional[str]:
    for attr in product.get("attributes", []) or []:
        if str(attr.get("name", "")).strip().lower() in _BRAND_ATTRS:
            opts = attr.get("options") or []
            if opts:
                return ", ".join(str(o) for o in opts)[:200]
    return None


def _category(product: dict) -> Optional[str]:
    cats = [c.get("name", "") for c in product.get("categories", []) or [] if c.get("name")]
    return ", ".join(cats)[:300] if cats else None


# Мета, которую сайт заполняет остатками поставщиков и показывает в карточке
# блоком «Наличие · Удалённый склад · 2 шт. Срок поставки 1-2 дн.».
# Формат значения: [{"warehouse": "Удалённый склад", "supplier": "PRSTH",
# "qty": 2, "lead_time_min": 1, "lead_time_max": 2}]. Пустой список — карточка
# пишет «По запросу», то есть на складе позиции нет.
_REMOTE_STOCK_META = "_remote_stock_blocks"


def _remote_stock_blocks(product: dict) -> Optional[list]:
    """Разобрать `_remote_stock_blocks`. None — меты нет / она не читается."""
    for m in product.get("meta_data") or []:
        if m.get("key") != _REMOTE_STOCK_META:
            continue
        val = m.get("value")
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except (TypeError, ValueError):
                return None
        return val if isinstance(val, list) else None
    return None


def _availability(product: dict) -> dict[str, Any]:
    """Наличие и срок поставки — или «неизвестно», если магазин их не даёт.

    Собственный учёт остатков в каталоге stalkerelectric.kz выключен: у всех
    30 тыс. товаров ``manage_stock: false`` и ``stock_quantity: null``, а
    ``stock_status`` равен "instock" просто по умолчанию — принимать это за
    наличие нельзя (MASTER WORKFLOW §5.5, §44.12: прайс не является
    подтверждением наличия). Единственные настоящие данные о наличии на сайте —
    блоки остатков поставщиков в мете ``_remote_stock_blocks``: у позиций с
    непустым блоком известны и количество, и срок поставки. У остальных карточка
    пишет «По запросу» — это НЕ подтверждённое отсутствие, а «уточняется»,
    поэтому возвращаем None, а не False.
    """
    out: dict[str, Any] = {"in_stock": None, "stock_qty": None, "lead_time_days": None}
    blocks = _remote_stock_blocks(product)
    if blocks:
        qty = 0.0
        leads = []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            try:
                qty += float(b.get("qty") or 0)
            except (TypeError, ValueError):
                pass
            for key in ("lead_time_max", "lead_time_min"):
                v = b.get(key)
                if isinstance(v, (int, float)):
                    leads.append(int(v))
                    break
        if qty > 0:
            out["in_stock"] = True
            out["stock_qty"] = qty
            # Берём худший срок из блоков — обещать более быстрый нельзя.
            out["lead_time_days"] = max(leads) if leads else None
            out["extra"] = {"remote_stock": blocks}
            return out
    status = product.get("stock_status")
    if status in ("outofstock", "onbackorder"):
        out["in_stock"] = False
        return out
    qty_wc = product.get("stock_quantity")
    if product.get("manage_stock") and qty_wc is not None:
        out["in_stock"] = qty_wc > 0
        out["stock_qty"] = qty_wc
    return out


def _to_offer(product: dict) -> dict:
    avail = _availability(product)
    return {
        "source_key": product.get("id"),
        "supplier_name": SITE_SUPPLIER_NAME,
        "article": (product.get("sku") or None),
        "name": product.get("name") or "Без названия",
        "brand": _brand(product),
        "category": _category(product),
        "price": _parse_price(product),
        "currency": "KZT",
        "in_stock": avail["in_stock"],
        "stock_qty": avail["stock_qty"],
        "lead_time_days": avail["lead_time_days"],
        "url": product.get("permalink") or None,
        "extra": avail.get("extra"),
    }


async def sync_site_offers(workspace_id: int = 1) -> dict:
    """Fetch all WooCommerce products and (re)build site offers.

    Returns stats. Raises if WooCommerce credentials are missing.
    """
    secrets = await woocommerce_service.get_config_with_secrets()
    if not secrets or not secrets.get("consumer_key"):
        raise RuntimeError("WooCommerce credentials not configured")

    products = await get_all_products(
        secrets["store_url"], secrets["consumer_key"], secrets["consumer_secret"]
    )
    offers = [_to_offer(p) for p in products]
    written = await offer_service.replace_source_offers(
        SOURCE_SITE, offers, workspace_id=workspace_id
    )
    logger.info("procurement site adapter: %d products -> %d offers", len(products), written)
    return {"products": len(products), "offers": written, "source": SOURCE_SITE}
