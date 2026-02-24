"""WooCommerce Dataset Service — transforms WooCommerce data into markdown for RAG indexing.

Pure functions: no DB access, no side effects (except file I/O in get/clean helpers).
"""

import re
from pathlib import Path
from typing import Any


WC_DIR = Path("data/woocommerce-dataset")
WC_FILE_PREFIX = "wc-"


def format_price_kzt(amount: str | int | float | None) -> str:
    """Format price in KZT with thousands separator."""
    if not amount:
        return "0 ₸"
    try:
        val = int(float(str(amount)))
    except (ValueError, TypeError):
        return "0 ₸"
    return f"{val:,} ₸".replace(",", " ")


def clean_html(text: str | None) -> str:
    """Strip HTML tags from WooCommerce description fields."""
    if not text:
        return ""
    # Remove HTML tags
    clean = re.sub(r"<[^>]+>", "", text)
    # Normalize whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    # Decode common HTML entities
    clean = (
        clean.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#8211;", "–")
        .replace("&#8212;", "—")
        .replace("&nbsp;", " ")
    )
    return clean


def _extract_categories(product: dict[str, Any]) -> str:
    """Extract category names from product."""
    categories = product.get("categories", [])
    if not categories:
        return "Без категории"
    return ", ".join(c.get("name", "") for c in categories if c.get("name"))


def _extract_attributes(product: dict[str, Any]) -> list[tuple[str, str]]:
    """Extract attribute name-value pairs from product."""
    result: list[tuple[str, str]] = []
    for attr in product.get("attributes", []):
        name = attr.get("name", "")
        options = attr.get("options", [])
        if name and options:
            result.append((name, ", ".join(str(o) for o in options)))
    return result


def _build_product_section(product: dict[str, Any]) -> str:
    """Build a ## section for a single product."""
    name = product.get("name", "Без названия")
    sku = product.get("sku", "")
    regular_price = product.get("regular_price", "")
    sale_price = product.get("sale_price", "")
    price = product.get("price", regular_price)
    stock_status = product.get("stock_status", "")
    permalink = product.get("permalink", "")
    short_desc = clean_html(product.get("short_description", ""))
    full_desc = clean_html(product.get("description", ""))
    categories = _extract_categories(product)
    pid = product.get("id", "")

    # Title with SKU and price
    title_parts = [f"## Товар: {name}"]
    if sku:
        title_parts[0] += f" (Артикул: {sku})"
    title_parts[0] += f" — {format_price_kzt(price)}"

    lines = title_parts + [""]
    lines.append(f"- **ID**: {pid}")
    lines.append(f"- **Категория**: {categories}")

    # Prices
    if regular_price:
        price_line = f"- **Цена**: {format_price_kzt(regular_price)}"
        if sale_price:
            price_line += f" (скидка: {format_price_kzt(sale_price)})"
        lines.append(price_line)
        # Raw digits for BM25 matching
        lines.append(f"- **Цена (число)**: {regular_price}")

    # Stock
    stock_map = {
        "instock": "В наличии",
        "outofstock": "Нет в наличии",
        "onbackorder": "Под заказ",
    }
    stock_qty = product.get("stock_quantity")
    stock_text = stock_map.get(stock_status, stock_status)
    if stock_qty is not None:
        stock_text += f" ({stock_qty} шт.)"
    lines.append(f"- **Наличие**: {stock_text}")

    if sku:
        lines.append(f"- **Артикул**: {sku}")

    # Description
    desc = short_desc or full_desc
    if desc:
        # Limit description to ~500 chars for RAG
        if len(desc) > 500:
            desc = desc[:500] + "..."
        lines.append(f"- **Описание**: {desc}")

    # Attributes
    attributes = _extract_attributes(product)
    for attr_name, attr_value in attributes:
        lines.append(f"- **{attr_name}**: {attr_value}")

    # Weight and dimensions
    weight = product.get("weight", "")
    if weight:
        lines.append(f"- **Вес**: {weight} кг")

    dimensions = product.get("dimensions", {})
    if dimensions:
        parts = []
        if dimensions.get("length"):
            parts.append(f"{dimensions['length']}×")
        if dimensions.get("width"):
            parts.append(f"{dimensions['width']}×")
        if dimensions.get("height"):
            parts.append(f"{dimensions['height']}")
        if parts:
            lines.append(f"- **Размеры**: {''.join(parts)} см")

    if permalink:
        lines.append(f"- **URL**: {permalink}")

    return "\n".join(lines)


def build_category_document(
    category: dict[str, Any],
    products: list[dict[str, Any]],
    sync_time: str,
) -> str:
    """Build markdown document for one category with its products."""
    cat_name = category.get("name", "Без названия")
    cat_desc = clean_html(category.get("description", ""))
    count = len(products)

    lines = [
        f"# Категория: {cat_name} ({count} товаров)",
        "",
        f"Данные из WooCommerce магазина. Последнее обновление: {sync_time}",
        "",
    ]

    if cat_desc:
        lines.append(cat_desc)
        lines.append("")

    if not products:
        lines.append("Товаров в этой категории нет.")
        return "\n".join(lines)

    # Sort by name
    products_sorted = sorted(products, key=lambda x: x.get("name", ""))
    for product in products_sorted:
        lines.append(_build_product_section(product))
        lines.append("")

    return "\n".join(lines)


def build_orders_document(
    orders: list[dict[str, Any]],
    sync_time: str,
) -> str:
    """Build markdown document with recent orders summary."""
    lines = [
        f"# Заказы WooCommerce ({len(orders)} заказов)",
        "",
        f"Данные из WooCommerce магазина. Последнее обновление: {sync_time}",
        "",
    ]

    if not orders:
        lines.append("Заказов нет.")
        return "\n".join(lines)

    # Status counts
    status_counts: dict[str, int] = {}
    total_revenue = 0.0
    for order in orders:
        status = order.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        try:
            total_revenue += float(order.get("total", 0))
        except (ValueError, TypeError):
            pass

    lines.append("## Статистика заказов")
    lines.append("")
    lines.append(f"- **Всего заказов**: {len(orders)}")
    lines.append(f"- **Общая сумма**: {format_price_kzt(total_revenue)}")
    lines.append("")

    status_names = {
        "pending": "Ожидает оплаты",
        "processing": "В обработке",
        "on-hold": "На удержании",
        "completed": "Выполнен",
        "cancelled": "Отменён",
        "refunded": "Возвращён",
        "failed": "Не удался",
    }

    lines.append("| Статус | Количество |")
    lines.append("|--------|-----------|")
    for status, count in status_counts.items():
        name = status_names.get(status, status)
        lines.append(f"| {name} | {count} |")
    lines.append("")

    # Recent orders (last 50)
    lines.append("## Последние заказы")
    lines.append("")
    recent = sorted(orders, key=lambda x: x.get("date_created", ""), reverse=True)[:50]
    for order in recent:
        oid = order.get("id", "")
        status = status_names.get(order.get("status", ""), order.get("status", ""))
        total = format_price_kzt(order.get("total", 0))
        date = order.get("date_created", "")[:10]
        billing = order.get("billing", {})
        customer = f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip()
        if not customer:
            customer = "Неизвестный"

        items = order.get("line_items", [])
        item_names = ", ".join(i.get("name", "") for i in items[:3])
        if len(items) > 3:
            item_names += f" и ещё {len(items) - 3}"

        lines.append(f"### Заказ #{oid} — {status} ({total})")
        lines.append(f"- **Дата**: {date}")
        lines.append(f"- **Клиент**: {customer}")
        if billing.get("phone"):
            lines.append(f"- **Телефон**: {billing['phone']}")
        if item_names:
            lines.append(f"- **Товары**: {item_names}")
        lines.append("")

    return "\n".join(lines)


def build_summary_document(
    products: list[dict[str, Any]],
    categories: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    sync_time: str,
    store_url: str = "",
) -> str:
    """Build the wc-summary.md with aggregate stats."""
    total_products = len(products)
    in_stock = sum(1 for p in products if p.get("stock_status") == "instock")

    lines = [
        "# WooCommerce: Сводка по магазину",
        "",
        f"Данные из WooCommerce магазина. Последнее обновление: {sync_time}",
        "",
    ]
    if store_url:
        lines.append(f"**Магазин**: {store_url}")
        lines.append("")

    lines.append("## Общая статистика")
    lines.append("")
    lines.append(f"- **Всего товаров**: {total_products}")
    lines.append(f"- **В наличии**: {in_stock}")
    lines.append(f"- **Категорий**: {len(categories)}")
    lines.append(f"- **Заказов**: {len(orders)}")
    lines.append("")

    # Price range
    prices = []
    for p in products:
        try:
            price = float(p.get("price") or p.get("regular_price") or 0)
            if price > 0:
                prices.append(price)
        except (ValueError, TypeError):
            pass

    if prices:
        lines.append("## Ценовой диапазон")
        lines.append("")
        lines.append(f"- **Минимальная цена**: {format_price_kzt(min(prices))}")
        lines.append(f"- **Максимальная цена**: {format_price_kzt(max(prices))}")
        lines.append(f"- **Средняя цена**: {format_price_kzt(sum(prices) / len(prices))}")
        lines.append("")

    # Categories breakdown
    if categories:
        lines.append("## Категории")
        lines.append("")
        lines.append("| Категория | Количество товаров |")
        lines.append("|-----------|-------------------|")
        cat_counts: dict[int, int] = {}
        for p in products:
            for cat in p.get("categories", []):
                cid = cat.get("id", 0)
                cat_counts[cid] = cat_counts.get(cid, 0) + 1
        cat_name_map = {c["id"]: c.get("name", "") for c in categories}
        for cid, count in sorted(cat_counts.items(), key=lambda x: x[1], reverse=True):
            cname = cat_name_map.get(cid, f"Категория {cid}")
            lines.append(f"| {cname} | {count} |")
        lines.append("")

    return "\n".join(lines)


def get_wc_filenames() -> list[str]:
    """List existing WooCommerce dataset files."""
    if not WC_DIR.exists():
        return []
    return [f.name for f in WC_DIR.glob(f"{WC_FILE_PREFIX}*.md")]


def clean_wc_files() -> list[str]:
    """Remove all existing WooCommerce dataset files. Returns removed filenames."""
    removed = []
    if not WC_DIR.exists():
        return removed
    for f in WC_DIR.glob(f"{WC_FILE_PREFIX}*.md"):
        f.unlink()
        removed.append(f.name)
    return removed
