"""Reusable WooCommerce dataset sync logic.

Used by both the manual API endpoint and the periodic auto-sync task.
"""

import logging
import re
from datetime import datetime

from app.services.woocommerce_dataset_service import (
    WC_DIR,
    build_category_document,
    build_orders_document,
    build_summary_document,
    clean_wc_files,
)
from app.services.woocommerce_service import (
    get_all_orders,
    get_all_products,
    get_categories,
)
from modules.ecommerce.service import woocommerce_service


logger = logging.getLogger(__name__)

WC_COLLECTION_SLUG = "woocommerce"
WC_COLLECTION_NAME = "WooCommerce"


async def run_woocommerce_sync() -> dict:
    """Core WooCommerce dataset sync.

    Fetches products/categories/orders, generates markdown files,
    updates knowledge collection + re-indexes BM25.

    Returns stats dict with keys: products, categories, orders,
    files_written, files_removed, collection_id, synced_at.

    Raises on credential or product-fetch failures.
    """
    secrets = await woocommerce_service.get_config_with_secrets()
    if not secrets or not secrets.get("consumer_key"):
        raise RuntimeError("WooCommerce credentials not configured")

    store_url = secrets["store_url"]
    ck = secrets["consumer_key"]
    cs = secrets["consumer_secret"]
    sync_time = datetime.utcnow().strftime("%d.%m.%Y %H:%M")

    # 1. Fetch data from WooCommerce
    all_products = await get_all_products(store_url, ck, cs)

    try:
        all_categories = await get_categories(store_url, ck, cs)
    except Exception as e:
        logger.warning("WooCommerce category fetch failed: %s", e)
        all_categories = []

    try:
        all_orders = await get_all_orders(store_url, ck, cs)
    except Exception as e:
        logger.warning("WooCommerce order fetch failed: %s", e)
        all_orders = []

    # 2. Group products by category
    cat_products: dict[int, list[dict]] = {c["id"]: [] for c in all_categories}
    uncategorized: list[dict] = []
    for product in all_products:
        placed = False
        for cat in product.get("categories", []):
            cid = cat.get("id")
            if cid in cat_products:
                cat_products[cid].append(product)
                placed = True
        if not placed:
            uncategorized.append(product)

    # 3. Clean old files
    removed = clean_wc_files()

    # 4. Generate and write documents
    WC_DIR.mkdir(parents=True, exist_ok=True)
    written_files: list[tuple[str, str, str]] = []  # (filename, content, title)

    for category in all_categories:
        cid = category["id"]
        products = cat_products.get(cid, [])
        if not products:
            continue
        content = build_category_document(category, products, sync_time)
        filename = f"wc-category-{cid}.md"
        (WC_DIR / filename).write_text(content, encoding="utf-8")
        written_files.append((filename, content, f"Категория: {category.get('name', '')}"))

    if uncategorized:
        content = build_category_document(
            {"name": "Без категории", "description": ""}, uncategorized, sync_time
        )
        filename = "wc-uncategorized.md"
        (WC_DIR / filename).write_text(content, encoding="utf-8")
        written_files.append((filename, content, "Без категории"))

    if all_orders:
        content = build_orders_document(all_orders, sync_time)
        filename = "wc-orders.md"
        (WC_DIR / filename).write_text(content, encoding="utf-8")
        written_files.append((filename, content, "Заказы WooCommerce"))

    summary_content = build_summary_document(
        all_products, all_categories, all_orders, sync_time, store_url
    )
    summary_filename = "wc-summary.md"
    (WC_DIR / summary_filename).write_text(summary_content, encoding="utf-8")
    written_files.append((summary_filename, summary_content, "WooCommerce: Сводка"))

    # 5. Publish DatasetSynced event — knowledge domain handles DB + RAG
    from app.dependencies import get_container
    from modules.core.events import DatasetSynced

    documents = []
    for filename, content, title in written_files:
        sections = len(re.findall(r"^#{2,3}\s+.+$", content, re.MULTILINE))
        documents.append(
            {
                "filename": filename,
                "title": title,
                "source_type": "woocommerce",
                "file_size_bytes": len(content.encode("utf-8")),
                "section_count": sections,
            }
        )

    try:
        await get_container().event_bus.publish(
            DatasetSynced(
                source="woocommerce",
                collection_slug=WC_COLLECTION_SLUG,
                action="synced",
                collection_name=WC_COLLECTION_NAME,
                collection_description=(
                    "Товары, категории и заказы из WooCommerce магазина (автосинхронизация)"
                ),
                base_dir=str(WC_DIR),
                documents=documents,
            )
        )
    except Exception as e:
        logger.warning("Failed to publish DatasetSynced: %s", e)

    # Resolve collection_id for response (read-only)
    from modules.knowledge.service import knowledge_collection_service

    collection = await knowledge_collection_service.get_by_slug(WC_COLLECTION_SLUG)
    collection_id = collection["id"] if collection else None

    # 6. Update config with counts
    await woocommerce_service.save_config(
        products_count=len(all_products),
        categories_count=len(all_categories),
        orders_count=len(all_orders),
        last_sync_at=sync_time,
        is_connected=True,
    )

    return {
        "products": len(all_products),
        "categories": len(all_categories),
        "orders": len(all_orders),
        "files_written": len(written_files),
        "files_removed": len(removed),
        "collection_id": collection_id,
        "synced_at": sync_time,
    }
