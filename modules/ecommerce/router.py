"""WooCommerce integration router — config, dataset sync, product browsing."""

import logging
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

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
    test_connection,
)
from auth_manager import User, require_permission
from modules.ecommerce.service import woocommerce_service
from modules.knowledge.service import knowledge_collection_service, knowledge_doc_service
from modules.monitoring.service import audit_service


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/woocommerce", tags=["woocommerce"])


# ============== Config ==============


@router.get("/config")
async def get_config(user: User = Depends(require_permission("sales", "view"))):
    """Get WooCommerce config (secrets masked)."""
    config = await woocommerce_service.get_config()
    if not config:
        return {"config": None}
    return {"config": config}


@router.post("/config")
async def save_config(
    data: dict,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Save WooCommerce config (store URL, credentials)."""
    allowed_fields = {"store_url", "consumer_key", "consumer_secret", "sync_enabled"}
    kwargs = {k: v for k, v in data.items() if k in allowed_fields}

    if not kwargs:
        raise HTTPException(status_code=400, detail="No valid fields provided")

    config = await woocommerce_service.save_config(**kwargs)

    await audit_service.log(
        action="update",
        resource="woocommerce_config",
        user_id=user.username,
        details={"fields": list(kwargs.keys())},
    )

    return {"status": "ok", "config": config}


@router.post("/test")
async def test_woocommerce_connection(
    user: User = Depends(require_permission("sales", "edit")),
):
    """Test connection to WooCommerce store."""
    secrets = await woocommerce_service.get_config_with_secrets()
    if not secrets or not secrets.get("consumer_key"):
        raise HTTPException(status_code=400, detail="WooCommerce credentials not configured")

    store_url = secrets["store_url"]
    ck = secrets["consumer_key"]
    cs = secrets["consumer_secret"]

    try:
        info = await test_connection(store_url, ck, cs)
    except Exception as e:
        logger.warning(f"WooCommerce connection test failed: {e}")
        raise HTTPException(status_code=400, detail=f"Connection failed: {e}")

    # Mark as connected
    await woocommerce_service.save_config(is_connected=True)

    return {"status": "ok", "store_info": info}


@router.post("/disconnect")
async def disconnect_woocommerce(
    user: User = Depends(require_permission("sales", "edit")),
):
    """Clear WooCommerce credentials."""
    await woocommerce_service.clear_credentials()

    await audit_service.log(
        action="disconnect",
        resource="woocommerce_config",
        user_id=user.username,
    )

    return {"status": "ok"}


# ============== Dataset Sync ==============

WC_COLLECTION_SLUG = "woocommerce"
WC_COLLECTION_NAME = "WooCommerce"


async def _get_credentials() -> tuple[str, str, str]:
    """Get and validate WooCommerce credentials."""
    secrets = await woocommerce_service.get_config_with_secrets()
    if not secrets or not secrets.get("consumer_key"):
        raise HTTPException(status_code=400, detail="WooCommerce credentials not configured")
    return secrets["store_url"], secrets["consumer_key"], secrets["consumer_secret"]


@router.post("/dataset-sync")
async def wc_dataset_sync(user: User = Depends(require_permission("sales", "edit"))):
    """Sync WooCommerce data into knowledge base for RAG.

    Fetches all products + categories + orders, generates markdown documents,
    writes to data/woocommerce-dataset/, updates knowledge collection + re-indexes.
    """
    store_url, ck, cs = await _get_credentials()
    sync_time = datetime.utcnow().strftime("%d.%m.%Y %H:%M")

    # 1. Fetch data from WooCommerce
    try:
        all_products = await get_all_products(store_url, ck, cs)
    except Exception as e:
        logger.error(f"WooCommerce product fetch failed: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to fetch products: {e}")

    try:
        all_categories = await get_categories(store_url, ck, cs)
    except Exception as e:
        logger.warning(f"WooCommerce category fetch failed: {e}")
        all_categories = []

    try:
        all_orders = await get_all_orders(store_url, ck, cs)
    except Exception as e:
        logger.warning(f"WooCommerce order fetch failed: {e}")
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

    # Per-category documents
    for category in all_categories:
        cid = category["id"]
        products = cat_products.get(cid, [])
        if not products:
            continue
        content = build_category_document(category, products, sync_time)
        filename = f"wc-category-{cid}.md"
        (WC_DIR / filename).write_text(content, encoding="utf-8")
        written_files.append((filename, content, f"Категория: {category.get('name', '')}"))

    # Uncategorized products
    if uncategorized:
        content = build_category_document(
            {"name": "Без категории", "description": ""}, uncategorized, sync_time
        )
        filename = "wc-uncategorized.md"
        (WC_DIR / filename).write_text(content, encoding="utf-8")
        written_files.append((filename, content, "Без категории"))

    # Orders document
    if all_orders:
        content = build_orders_document(all_orders, sync_time)
        filename = "wc-orders.md"
        (WC_DIR / filename).write_text(content, encoding="utf-8")
        written_files.append((filename, content, "Заказы WooCommerce"))

    # Summary document
    summary_content = build_summary_document(
        all_products, all_categories, all_orders, sync_time, store_url
    )
    summary_filename = "wc-summary.md"
    (WC_DIR / summary_filename).write_text(summary_content, encoding="utf-8")
    written_files.append((summary_filename, summary_content, "WooCommerce: Сводка"))

    # 5. Ensure "woocommerce" collection exists
    collection = await knowledge_collection_service.get_by_slug(WC_COLLECTION_SLUG)
    if not collection:
        collection = await knowledge_collection_service.create(
            name=WC_COLLECTION_NAME,
            slug=WC_COLLECTION_SLUG,
            description="Товары, категории и заказы из WooCommerce магазина (автосинхронизация)",
            enabled=True,
            base_dir="data/woocommerce-dataset",
        )
    collection_id = collection["id"]

    # 6. Remove old DB records, create new ones
    existing_docs = await knowledge_doc_service.get_by_collection(collection_id)
    for doc in existing_docs:
        await knowledge_doc_service.delete(doc["id"])

    for filename, content, title in written_files:
        sections = len(re.findall(r"^#{2,3}\s+.+$", content, re.MULTILINE))
        await knowledge_doc_service.create(
            filename=filename,
            title=title,
            source_type="woocommerce",
            file_size_bytes=len(content.encode("utf-8")),
            section_count=sections,
            collection_id=collection_id,
        )

    # 7. Re-index the collection in WikiRAG
    from app.dependencies import get_container

    container = get_container()
    wiki_rag = container.wiki_rag_service
    if wiki_rag:
        filenames = [f[0] for f in written_files]
        wiki_rag.reload_collection(collection_id, filenames, WC_DIR)

    # 8. Update config with counts
    await woocommerce_service.save_config(
        products_count=len(all_products),
        categories_count=len(all_categories),
        orders_count=len(all_orders),
        last_sync_at=sync_time,
        is_connected=True,
    )

    await audit_service.log(
        action="dataset_sync",
        resource="woocommerce",
        user_id=user.username,
        details={
            "products": len(all_products),
            "categories": len(all_categories),
            "orders": len(all_orders),
            "files": len(written_files),
        },
    )

    return {
        "status": "ok",
        "products": len(all_products),
        "categories": len(all_categories),
        "orders": len(all_orders),
        "files_written": len(written_files),
        "files_removed": len(removed),
        "collection_id": collection_id,
        "synced_at": sync_time,
    }


@router.get("/dataset-status")
async def wc_dataset_status(user: User = Depends(require_permission("sales", "view"))):
    """Get WooCommerce dataset sync status."""
    collection = await knowledge_collection_service.get_by_slug(WC_COLLECTION_SLUG)
    if not collection:
        return {
            "synced": False,
            "collection_id": None,
            "documents": 0,
            "total_sections": 0,
            "last_sync": None,
            "files": [],
        }

    docs = await knowledge_doc_service.get_by_collection(collection["id"])

    # Get last_sync from config
    config = await woocommerce_service.get_config()
    last_sync = config.get("last_sync_at") if config else None

    return {
        "synced": len(docs) > 0,
        "collection_id": collection["id"],
        "collection_name": collection["name"],
        "documents": len(docs),
        "total_sections": sum(d.get("section_count", 0) for d in docs),
        "last_sync": last_sync,
        "files": [d["filename"] for d in docs],
    }


@router.delete("/dataset")
async def wc_dataset_clear(user: User = Depends(require_permission("sales", "manage"))):
    """Clear WooCommerce dataset."""
    collection = await knowledge_collection_service.get_by_slug(WC_COLLECTION_SLUG)
    if collection:
        # Remove DB records
        docs = await knowledge_doc_service.get_by_collection(collection["id"])
        for doc in docs:
            await knowledge_doc_service.delete(doc["id"])

        # Clear RAG index
        from app.dependencies import get_container

        container = get_container()
        wiki_rag = container.wiki_rag_service
        if wiki_rag:
            wiki_rag.reload_collection(collection["id"], [], WC_DIR)

    # Remove files
    removed = clean_wc_files()

    # Reset config counts
    await woocommerce_service.save_config(
        products_count=0,
        categories_count=0,
        orders_count=0,
        last_sync_at=None,
    )

    await audit_service.log(
        action="dataset_clear",
        resource="woocommerce",
        user_id=user.username,
    )

    return {"status": "ok", "files_removed": len(removed)}
