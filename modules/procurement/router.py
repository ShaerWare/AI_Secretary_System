"""Procurement router — unified offer search + site-offer sync (admin).

Read/inspect surface for the single-search pipeline. The sales assistant will
consume `offer_service.search` server-side; these endpoints let admins verify
coverage and trigger a manual site sync.
"""

import logging

from fastapi import APIRouter, Depends

from auth_manager import User, require_permission
from modules.monitoring.service import audit_service
from modules.procurement.models import SOURCE_EKF, SOURCE_SITE, SOURCE_SUPPLIER
from modules.procurement.service import offer_service
from modules.procurement.site_adapter import sync_site_offers


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/procurement", tags=["procurement"])


@router.get("/status")
async def procurement_status(user: User = Depends(require_permission("sales", "view"))):
    """Offer counts per source."""
    return {
        "sources": {
            SOURCE_SITE: await offer_service.count(source=SOURCE_SITE),
            SOURCE_EKF: await offer_service.count(source=SOURCE_EKF),
            SOURCE_SUPPLIER: await offer_service.count(source=SOURCE_SUPPLIER),
        },
        "total": await offer_service.count(),
    }


@router.get("/search")
async def procurement_search(
    q: str,
    limit: int = 10,
    in_stock_only: bool = False,
    user: User = Depends(require_permission("sales", "view")),
):
    """Unified deterministic offer search. Returns [] if nothing matches."""
    results = await offer_service.search(q, limit=limit, in_stock_only=in_stock_only)
    return {"query": q, "count": len(results), "results": results}


@router.post("/sync")
async def procurement_sync_site(user: User = Depends(require_permission("sales", "edit"))):
    """Manually rebuild site offers from the WooCommerce catalog."""
    result = await sync_site_offers()
    await audit_service.log(
        action="sync",
        resource="procurement_offers",
        resource_id=SOURCE_SITE,
        user_id=user.username,
        details=result,
    )
    return result
