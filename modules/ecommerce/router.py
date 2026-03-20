"""WooCommerce integration router — config, dataset sync, product browsing."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.services.woocommerce_dataset_service import WC_DIR, clean_wc_files
from app.services.woocommerce_service import test_connection
from auth_manager import User, require_permission
from modules.ecommerce.service import woocommerce_service
from modules.ecommerce.sync import run_woocommerce_sync
from modules.knowledge.service import knowledge_collection_service, knowledge_doc_service
from modules.monitoring.service import audit_service


# knowledge_collection_service and knowledge_doc_service are used only for
# read-only dataset-status queries; mutations go through DatasetSynced events.


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


@router.post("/dataset-sync")
async def wc_dataset_sync(user: User = Depends(require_permission("sales", "edit"))):
    """Sync WooCommerce data into knowledge base for RAG.

    Fetches all products + categories + orders, generates markdown documents,
    writes to data/woocommerce-dataset/, updates knowledge collection + re-indexes.
    """
    try:
        result = await run_woocommerce_sync()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("WooCommerce sync failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Sync failed: {e}")

    await audit_service.log(
        action="dataset_sync",
        resource="woocommerce",
        user_id=user.username,
        details={
            "products": result["products"],
            "categories": result["categories"],
            "orders": result["orders"],
            "files": result["files_written"],
        },
    )

    return {"status": "ok", **result}


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
    # Remove files
    removed = clean_wc_files()

    # Publish DatasetSynced(cleared) — knowledge domain handles DB + RAG
    from app.dependencies import get_container
    from modules.core.events import DatasetSynced

    try:
        await get_container().event_bus.publish(
            DatasetSynced(
                source="woocommerce",
                collection_slug=WC_COLLECTION_SLUG,
                action="cleared",
                base_dir=str(WC_DIR),
            )
        )
    except Exception as e:
        logger.warning("Failed to publish DatasetSynced(cleared): %s", e)

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
