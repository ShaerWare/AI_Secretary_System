"""Procurement domain background tasks: periodic site-offer sync.

Rebuilds structured `product_offers` from the WooCommerce catalog daily,
shortly after the WooCommerce dataset sync (23:00 UTC), so the unified search
reflects fresh prices/stock.
"""

import asyncio
import logging
from datetime import datetime, timedelta


logger = logging.getLogger(__name__)


async def procurement_site_sync() -> None:
    """Daily site-offer sync at 23:30 UTC (after woocommerce-sync at 23:00).

    Self-scheduling loop (TaskRegistry has no cron support).
    """
    await asyncio.sleep(180)  # warmup, and let woocommerce-sync go first
    while True:
        now = datetime.utcnow()
        target = now.replace(hour=23, minute=30, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        logger.info("procurement site-offer sync scheduled in %.1fh", wait_seconds / 3600)
        await asyncio.sleep(wait_seconds)
        try:
            from modules.ecommerce.service import woocommerce_service
            from modules.procurement.site_adapter import sync_site_offers

            config = await woocommerce_service.get_config()
            if not config or not config.get("sync_enabled"):
                continue
            result = await sync_site_offers()
            logger.info(
                "procurement site-offer sync: %d products -> %d offers",
                result["products"],
                result["offers"],
            )
        except Exception as e:
            logger.warning("procurement site-offer sync error: %s", e)
            await asyncio.sleep(3600)  # on error retry in 1h
