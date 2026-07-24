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


@router.get("/price")
async def procurement_price(
    q: str,
    limit: int = 10,
    user: User = Depends(require_permission("sales", "view")),
):
    """Search + compute purchase/client (КП) prices per supplier rules.

    Manager view — includes dealer prices + computed client price + margin flag.
    """
    from modules.procurement.pricing import price_offer
    from modules.procurement.rate_service import get_usd_kzt

    offers = await offer_service.search(q, limit=limit)
    rate_info = await get_usd_kzt()
    results = []
    for o in offers:
        if o["source"] == "supplier":
            o["pricing"] = await price_offer(o, rate_info=rate_info)
        else:
            o["pricing"] = {"ok": False, "reason": "site_retail"}
        results.append(o)
    return {"query": q, "rate": rate_info, "count": len(results), "results": results}


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


@router.post("/sync-suppliers")
async def procurement_sync_suppliers(user: User = Depends(require_permission("sales", "edit"))):
    """Rebuild supplier offers from configured price files (SUPPLIER_PRICES_DIR)."""
    from modules.procurement.suppliers.adapter import sync_all_suppliers

    results = await sync_all_suppliers()
    await audit_service.log(
        action="sync",
        resource="procurement_offers",
        resource_id=SOURCE_SUPPLIER,
        user_id=user.username,
        details={"suppliers": results},
    )
    return {"suppliers": results}
