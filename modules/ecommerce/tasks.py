"""E-commerce domain background tasks: periodic WooCommerce sync."""

import asyncio
import logging
from datetime import datetime, timedelta


logger = logging.getLogger(__name__)


async def woocommerce_daily_sync() -> None:
    """Sync WooCommerce products/files daily at 23:00 UTC (02:00 MSK).

    This task manages its own schedule internally because TaskRegistry
    does not support cron-style scheduling. Registered as a one-shot
    task with an infinite loop.
    """
    await asyncio.sleep(120)  # warmup
    while True:
        now = datetime.utcnow()
        target = now.replace(hour=23, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        logger.info("WooCommerce auto-sync scheduled in %.1fh", wait_seconds / 3600)
        await asyncio.sleep(wait_seconds)
        try:
            from modules.ecommerce.service import woocommerce_service
            from modules.ecommerce.sync import run_woocommerce_sync

            config = await woocommerce_service.get_config()
            if not config or not config.get("sync_enabled"):
                continue
            result = await run_woocommerce_sync()
            logger.info(
                "WooCommerce auto-sync: %d products, %d files",
                result["products"],
                result["files_written"],
            )
        except Exception as e:
            logger.warning("WooCommerce auto-sync error: %s", e)
            await asyncio.sleep(3600)  # on error retry in 1h
