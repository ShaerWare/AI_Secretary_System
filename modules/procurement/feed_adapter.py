"""YML-фид наличия StalkerElectric: остатки и сроки поверх каталога сайта.

Фид (формат Яндекс.Маркета, отдаёт сторона клиента) перечисляет ТОЛЬКО то, что
реально доступно к заказу: у всех позиций ``available="true"``, ``count >= 1`` и
param «Срок поставки» в днях. Это ровно тот источник наличия, которого каталогу
не хватало: WooCommerce собственный учёт не ведёт (``manage_stock`` выключен у
всех товаров), и наличие приходилось вытаскивать из пер-поставщиковых мет.

**Фид не отдельный каталог, а слой поверх site-офферов.** Замер на живой базе
(11.10.2026): 2 293 из 2 299 ``vendorCode`` совпали с ``sku`` сайта, цена
совпала у ВСЕХ 2 293 до тенге, противоречий по наличию нет ни одного (ни одной
строки, где сайт говорит «нет», а фид «есть»), а у 964 позиций наличие у нас
было неизвестно — фид его подтверждает. Поэтому позиции накладываются на
существующие строки сайта по артикулу, а не вставляются рядом: отдельный
``source`` дал бы по два почти одинаковых оффера на товар и съел бы окно
выдачи (в поиск уходит 8 позиций).

Артикулы, которых в каталоге нет (на замере — 6), пишутся как
``source='feed'``: терять их нельзя, а дублировать нечего.

Порядок в суточном конвейере важен: сайт (23:30) полностью перестраивает свои
строки из WooCommerce, фид (23:40) накладывает наличие, поставщики (23:50)
пишут свои строки. Если прогон фида однажды упадёт, вчерашняя пометка уже
снята синком каталога — позиция уйдёт в «наличие уточняется», а не останется
обещать склад, которого нет. Это безопасная сторона отказа.
"""

import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx

from modules.procurement.models import SOURCE_FEED, SOURCE_SITE
from modules.procurement.service import offer_service


logger = logging.getLogger(__name__)

FEED_URL = os.getenv("PROCUREMENT_FEED_URL", "")
FEED_DIR = Path(os.getenv("PROCUREMENT_FEED_DATASET_DIR", "data/stalker-feed-dataset"))
FEED_FILE_PREFIX = "feed-"

FEED_COLLECTION_SLUG = "stalker-stock"
FEED_COLLECTION_NAME = "Stalker Electric — наличие (фид)"
FEED_COLLECTION_DESC = (
    "Позиции, доступные к заказу по фиду наличия: цена, количество и срок "
    "поставки. Обновляется ежесуточно."
)

# «1-3» → 3, «1» → 1: берём ВЕРХНЮЮ границу, как и у пер-поставщиковых мет
# каталога — обещать клиенту нижнюю границу диапазона нельзя.
_LEAD_RE = re.compile(r"(\d+)\s*(?:[-–—]\s*(\d+))?")


def _lead_days(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    m = _LEAD_RE.search(text)
    if not m:
        return None
    return int(m.group(2) or m.group(1))


def _text(node: ET.Element, tag: str) -> Optional[str]:
    el = node.find(tag)
    return (el.text or "").strip() if el is not None and el.text else None


def _number(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value.replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


def parse_feed(xml_bytes: bytes) -> dict:
    """Разобрать YML в ``{as_of, items, skipped}``. Чужой формат — не домысливаем.

    Позиции с ``available="false"`` отбрасываются: фид их не присылает, но если
    однажды пришлёт — «доступно» про них говорить нельзя.
    """
    root = ET.fromstring(xml_bytes)
    categories = {c.get("id"): (c.text or "").strip() for c in root.iter("category") if c.get("id")}

    items: list[dict] = []
    skipped = 0
    for offer in root.iter("offer"):
        if (offer.get("available") or "").lower() == "false":
            skipped += 1
            continue
        name = _text(offer, "name")
        article = _text(offer, "vendorCode") or offer.get("id")
        if not name or not article:
            skipped += 1
            continue
        lead = None
        for param in offer.findall("param"):
            if (param.get("name") or "").lower().startswith("срок"):
                lead = _lead_days(param.text)
                break
        items.append(
            {
                "source_key": offer.get("id") or article,
                "article": article,
                "name": name,
                "brand": _text(offer, "vendor"),
                "category": categories.get(_text(offer, "categoryId") or ""),
                "price": _number(_text(offer, "price")),
                "currency": _text(offer, "currencyId") or "KZT",
                # Фид перечисляет только доступное, поэтому наличие здесь —
                # утверждение самого источника, а не наша догадка.
                "in_stock": True,
                "stock_qty": _number(_text(offer, "count")),
                "lead_time_days": lead,
            }
        )

    if skipped:
        logger.info("procurement feed: пропущено позиций: %d", skipped)
    return {"as_of": root.get("date"), "items": items, "skipped": skipped}


async def fetch_feed(url: str) -> bytes:
    """Скачать фид. ~1 МБ, поэтому целиком в память."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=180.0)) as client:
        resp = await client.get(url, headers={"User-Agent": "ai-secretary-feed/1.0"})
        resp.raise_for_status()
        return resp.content


def _item_section(item: dict) -> str:
    price = f"{item['price']:g} ₸" if item.get("price") else "цена не указана"
    lines = [f"## {item['name']} (Артикул: {item['article']}) — {price}", ""]
    lines.append(f"- **Артикул**: {item['article']}")
    if item.get("brand"):
        lines.append(f"- **Производитель**: {item['brand']}")
    if item.get("category"):
        lines.append(f"- **Категория**: {item['category']}")
    if item.get("price"):
        lines.append(f"- **Цена**: {price}")
        # Голое число — для BM25, как в выгрузке WooCommerce.
        lines.append(f"- **Цена (число)**: {item['price']:g}")
    qty = f" {item['stock_qty']:g} шт." if item.get("stock_qty") else ""
    lines.append(f"- **Наличие**: доступно к заказу{qty}")
    if item.get("lead_time_days"):
        lines.append(f"- **Срок поставки**: до {item['lead_time_days']} дн.")
    return "\n".join(lines)


def _slugify(text: str) -> str:
    """Латиница для имени файла; у категорий фида она кириллическая."""
    translit = {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "c",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
    latin = "".join(translit.get(ch, ch) for ch in (text or "").lower())
    return re.sub(r"[^a-z0-9]+", "-", latin).strip("-") or "misc"


def build_documents(items: list[dict], as_of: str) -> list[tuple[str, str, str]]:
    """Собрать md по категориям + сводку → ``[(filename, content, title)]``."""
    by_category: dict[str, list[dict]] = {}
    for item in items:
        by_category.setdefault(item.get("category") or "Без категории", []).append(item)

    docs: list[tuple[str, str, str]] = []
    for idx, (category, rows) in enumerate(sorted(by_category.items())):
        body = [
            f"# В наличии: {category} ({len(rows)} позиций)",
            "",
            f"Позиции, доступные к заказу. Фид наличия, обновлён {as_of}.",
            "",
        ]
        for row in sorted(rows, key=lambda r: r["name"]):
            body.append(_item_section(row))
            body.append("")
        filename = f"{FEED_FILE_PREFIX}{idx:02d}-{_slugify(category)[:40]}.md"
        docs.append((filename, "\n".join(body), f"В наличии: {category}"))

    brands: dict[str, int] = {}
    for item in items:
        key = item.get("brand") or "—"
        brands[key] = brands.get(key, 0) + 1
    summary = [
        f"# Наличие Stalker Electric: сводка ({len(items)} позиций)",
        "",
        f"Фид наличия, обновлён {as_of}. Перечислены только позиции, доступные к заказу.",
        "",
        "## Производители",
        "",
    ]
    summary += [f"- {b}: {n} позиций" for b, n in sorted(brands.items(), key=lambda x: -x[1])]
    summary += ["", "## Категории", ""]
    summary += [
        f"- {c}: {len(r)} позиций" for c, r in sorted(by_category.items(), key=lambda x: -len(x[1]))
    ]
    docs.append((f"{FEED_FILE_PREFIX}summary.md", "\n".join(summary), "Наличие: сводка"))

    return docs


def _write_dataset(docs: list[tuple[str, str, str]]) -> list[dict]:
    """Записать md-файлы, убрав файлы прошлого прогона. Возвращает метаданные."""
    FEED_DIR.mkdir(parents=True, exist_ok=True)
    fresh = {fn for fn, _, _ in docs}
    for stale in FEED_DIR.glob(f"{FEED_FILE_PREFIX}*.md"):
        if stale.name not in fresh:
            stale.unlink()

    meta = []
    for filename, content, title in docs:
        (FEED_DIR / filename).write_text(content, encoding="utf-8")
        meta.append(
            {
                "filename": filename,
                "title": title,
                "source_type": "feed",
                "file_size_bytes": len(content.encode("utf-8")),
                "section_count": len(re.findall(r"^##\s+.+$", content, re.MULTILINE)),
            }
        )
    return meta


async def _publish_dataset(documents: list[dict]) -> None:
    from app.dependencies import get_container
    from modules.core.events import DatasetSynced

    await get_container().event_bus.publish(
        DatasetSynced(
            source="feed",
            collection_slug=FEED_COLLECTION_SLUG,
            action="synced",
            collection_name=FEED_COLLECTION_NAME,
            collection_description=FEED_COLLECTION_DESC,
            base_dir=str(FEED_DIR),
            documents=documents,
        )
    )


def _unmatched_offers(items: list[dict], matched_articles: set[str]) -> list[dict]:
    """Позиции фида, которых в каталоге сайта нет — отдельными строками."""
    return [
        {**item, "supplier_name": None, "extra": {"stock_source": "feed"}}
        for item in items
        if item["article"] not in matched_articles
    ]


async def sync_feed_offers(url: Optional[str] = None, workspace_id: int = 1) -> dict[str, Any]:
    """Забрать фид: наличие поверх каталога + RAG-коллекция. Возвращает статистику."""
    feed_url = url or FEED_URL
    if not feed_url:
        raise RuntimeError("PROCUREMENT_FEED_URL не задан")

    raw = await fetch_feed(feed_url)
    parsed = parse_feed(raw)
    items = parsed["items"]
    as_of = parsed["as_of"] or datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    if not items:
        raise RuntimeError("фид разобран, но позиций в нём нет")

    overlay = await offer_service.apply_feed_stock(
        items, target_source=SOURCE_SITE, workspace_id=workspace_id, as_of=as_of
    )

    extra_rows = _unmatched_offers(items, overlay["matched_articles"])
    written = await offer_service.replace_source_offers(
        SOURCE_FEED, extra_rows, workspace_id=workspace_id
    )

    documents = _write_dataset(build_documents(items, as_of))
    try:
        await _publish_dataset(documents)
    except Exception as e:
        logger.warning("procurement feed: DatasetSynced не опубликован: %s", e)

    stats = {
        "feed_items": len(items),
        "as_of": as_of,
        "site_rows_updated": overlay["updated"],
        "site_marks_cleared": overlay["cleared"],
        "own_rows": written,
        "documents": len(documents),
    }
    logger.info("procurement feed: %s", json.dumps(stats, ensure_ascii=False))
    return stats
