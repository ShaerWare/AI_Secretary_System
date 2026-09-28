"""Site adapter: WooCommerce catalog -> structured ProductOffer rows.

The first of three unified-search sources. Reuses the existing WooCommerce
client + stored credentials, so no new access is needed. EKF and supplier
adapters plug into the same `offer_service.replace_source_offers` interface.
"""

import json
import logging
import re
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


# Остатки поставщиков сайт держит двумя способами, и они расходятся.
#
# 1) Пер-поставщиковые меты — по полю на склад плюс срок доставки рядом:
#    `EKF_Stock_0` + `EKF_Stock_0_delivery` («1-2 дня»), `Chint_Stock_0` +
#    `Chint_Stock_0_delivery` («3-4 дня»), `Axima_Stock_0`/`Axima_Stock_2` +
#    их `_delivery` («1 день»). Остаток — строка с целым числом.
# 2) `_remote_stock_blocks` — сводка, которую рисует тема.
#
# Читаем ПЕРВЫЕ. Сводка после смены темы разъехалась с исходными полями и
# врёт в обе стороны: срок в ней прибит константой `1-2 дн.` для КАЖДОГО
# поставщика (у Chint собственное поле говорит «3-4 дня» — так в 39 случаях
# из 40), а количество расходится с пер-поставщиковыми полями в 67 случаях
# из 77 — вплоть до «AXIMA 28 шт.» там, где оба склада Аксимы дают ноль.
# Сводке оставлена одна работа: поставщики, у которых своей меты нет
# (ПРОМСИТЕХ). Срок оттуда не берём никогда — это не данные, а константа.
_REMOTE_STOCK_META = "_remote_stock_blocks"

# supplier -> (поля остатков по складам, поля срока)
_SUPPLIER_STOCK: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    # В сводке этот поставщик подписан SUNWELL — это тот же партнёр.
    "EKF": (("EKF_Stock_0",), ("EKF_Stock_0_delivery",)),
    "Chint": (("Chint_Stock_0",), ("Chint_Stock_0_delivery",)),
    "Axima": (
        ("Axima_Stock_0", "Axima_Stock_2"),
        ("Axima_Stock_0_delivery", "Axima_Stock_2_delivery"),
    ),
}

# Как поставщик подписан в сводке — чтобы не подобрать оттуда того, чьи
# собственные поля мы уже прочитали.
_BLOCK_SUPPLIER_ALIASES = {"SUNWELL": "EKF", "EKF": "EKF", "CHINT": "Chint", "AXIMA": "Axima"}


def _meta(product: dict) -> dict:
    """Меты товара словарём. Ключи не уникальны только у повторяющихся полей,
    которых здесь нет, поэтому последнее значение выигрывает."""
    out: dict = {}
    for m in product.get("meta_data") or []:
        key = m.get("key")
        if key is not None:
            out[str(key)] = m.get("value")
    return out


def _int_or_none(value) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return None


def _delivery_days(value) -> Optional[int]:
    """«1 день» → 1, «1-2 дня» → 2, «3-4 дня» → 4.

    Берём ВЕРХНЮЮ границу: обещать клиенту быстрее, чем сказал поставщик,
    нельзя. Строка без чисел — срока не знаем.
    """
    if not isinstance(value, str):
        return None
    numbers = [int(x) for x in re.findall(r"\d+", value)]
    return max(numbers) if numbers else None


def _supplier_readings(meta: dict) -> list[dict]:
    """Что каждый поставщик говорит про эту позицию.

    Возвращает только тех, у кого поле вообще есть: отсутствие поля — это
    «не знаем», а не «нет на складе».
    """
    readings = []
    for supplier, (qty_keys, delivery_keys) in _SUPPLIER_STOCK.items():
        present = [k for k in qty_keys if k in meta]
        if not present:
            continue
        qty = sum(_int_or_none(meta[k]) or 0 for k in present)
        days = [d for d in (_delivery_days(meta.get(k)) for k in delivery_keys) if d is not None]
        readings.append(
            {
                "supplier": supplier,
                "qty": qty,
                # Худший срок среди складов этого поставщика.
                "lead_time_days": max(days) if days else None,
            }
        )
    return readings


def _remote_stock_blocks(product: dict) -> Optional[list]:
    """Разобрать `_remote_stock_blocks`. None — меты нет / она не читается."""
    value = _meta(product).get(_REMOTE_STOCK_META)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return None
    return value if isinstance(value, list) else None


def _untracked_block_qty(product: dict) -> Optional[int]:
    """Остаток из сводки — только по поставщикам без собственных полей.

    Сегодня это ПРОМСИТЕХ. Срок из сводки не возвращаем: там константа.
    """
    total = 0
    found = False
    for block in _remote_stock_blocks(product) or []:
        if not isinstance(block, dict):
            continue
        supplier = str(block.get("supplier") or "").upper()
        if supplier in _BLOCK_SUPPLIER_ALIASES:
            continue
        qty = _int_or_none(block.get("qty"))
        if qty is not None:
            found = True
            total += qty
    return total if found else None


def _availability(product: dict) -> dict[str, Any]:
    """Наличие и срок поставки — или «неизвестно», если сайт их не даёт.

    Собственный складской учёт магазина бесполезен: `manage_stock` выключен у
    всех товаров, `stock_status` равен "instock" по умолчанию у всех 30 тыс.
    Принимать это за наличие нельзя (MASTER WORKFLOW §5.5, §44.12).

    Когда позиция есть у нескольких поставщиков, берём САМОГО БЫСТРОГО из тех,
    у кого она реально в наличии, и показываем его остаток с его же верхней
    границей срока. Суммировать склады разных поставщиков нельзя: «12 шт.,
    срок до 2 дн.» означало бы, что все двенадцать приедут за два дня, хотя
    семь из них лежат у поставщика с четырёхдневной доставкой.

    Все известные поставщики ответили «ноль» — это НЕ «нет в наличии»:
    позицию может возить тот, чьих полей на сайте нет. Возвращаем None, то
    есть «уточняется», а не отказ клиенту.
    """
    out: dict[str, Any] = {"in_stock": None, "stock_qty": None, "lead_time_days": None}
    meta = _meta(product)
    readings = _supplier_readings(meta)
    in_stock_now = [r for r in readings if r["qty"] > 0]

    if in_stock_now:
        # Без срока — в конец: позиция с известным сроком полезнее клиенту.
        best = min(in_stock_now, key=lambda r: (r["lead_time_days"] is None, r["lead_time_days"]))
        out["in_stock"] = True
        out["stock_qty"] = best["qty"]
        out["lead_time_days"] = best["lead_time_days"]
        out["extra"] = {"suppliers": readings}
        return out

    fallback_qty = _untracked_block_qty(product)
    if fallback_qty is not None and fallback_qty > 0:
        out["in_stock"] = True
        out["stock_qty"] = fallback_qty
        # Срок сводки — константа, а не данные: пусть менеджер уточнит.
        out["extra"] = {"remote_stock": _remote_stock_blocks(product)}
        return out

    if readings:
        # Поля есть и все по нулям — знаем только то, что у ЭТИХ поставщиков
        # позиции нет. Про товар в целом это ещё не «нет в наличии».
        out["extra"] = {"suppliers": readings}

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
