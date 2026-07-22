"""Site adapter: WooCommerce catalog -> structured ProductOffer rows.

The first of three unified-search sources. Reuses the existing WooCommerce
client + stored credentials, so no new access is needed. EKF and supplier
adapters plug into the same `offer_service.replace_source_offers` interface.
"""

import logging
from typing import Optional

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


def _to_offer(product: dict) -> dict:
    return {
        "source_key": product.get("id"),
        "supplier_name": SITE_SUPPLIER_NAME,
        "article": (product.get("sku") or None),
        "name": product.get("name") or "Без названия",
        "brand": _brand(product),
        "category": _category(product),
        "price": _parse_price(product),
        "currency": "KZT",
        "in_stock": product.get("stock_status") == "instock",
        "stock_qty": product.get("stock_quantity"),
        "url": product.get("permalink") or None,
        "extra": None,
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
