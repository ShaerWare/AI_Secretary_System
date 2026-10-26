"""Procurement domain background tasks: periodic offer syncs.

Rebuilds structured `product_offers` daily — из каталога WooCommerce
(23:30 UTC, вскоре после `woocommerce-sync`), из YML-фида наличия (23:40 UTC,
поверх каталога) и из файлов прайсов поставщиков (23:50 UTC), чтобы единый
поиск видел свежие цены, остатки и сроки.
"""

import asyncio
import logging
from datetime import datetime, timedelta


logger = logging.getLogger(__name__)


def _seconds_until(hour: int, minute: int) -> float:
    """Сколько ждать до ближайшего HH:MM UTC. TaskRegistry крона не умеет."""
    now = datetime.utcnow()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


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


async def procurement_supplier_sync() -> None:
    """Ежесуточный ре-парсинг прайсов поставщиков в 23:50 UTC.

    Без задачи прайсы разбирались только руками через
    `POST /admin/procurement/sync-suppliers`, и положенный в папку свежий файл
    никто не подхватывал: офферы поставщиков на проде простояли нетронутыми с
    24.07 по 28.09.2026. Папка задаётся env `SUPPLIER_PRICES_DIR`; файлов нет —
    парсер поднимает FileNotFoundError на каждом поставщике, `sync_all_suppliers`
    их логирует и не роняет остальных, поэтому пустая папка это не авария.

    Идёт после каталога (23:30): оба источника пишут в одну таблицу, и
    расходиться по времени им дешевле, чем толкаться.
    """
    await asyncio.sleep(240)  # warmup, и пропускаем вперёд синк каталога
    while True:
        wait_seconds = _seconds_until(23, 50)
        logger.info("procurement supplier sync scheduled in %.1fh", wait_seconds / 3600)
        await asyncio.sleep(wait_seconds)
        try:
            from modules.knowledge.drive_sources import pull_price_sources
            from modules.procurement.suppliers.adapter import sync_all_suppliers

            # Сначала свежие файлы с Google Диска (если источник подключён и там
            # что-то поменялось), потом разбор — в одной задаче, чтобы доставка
            # не могла прийти после парсинга.
            try:
                pulled = await pull_price_sources()
                if pulled:
                    logger.info("price files from Drive: %s", pulled)
            except Exception as e:
                logger.warning("price files from Drive failed, parsing what we have: %s", e)

            stats = await sync_all_suppliers()
            written = sum(int(s.get("offers") or 0) for s in stats)
            failed = [s.get("supplier") for s in stats if s.get("error")]
            logger.info(
                "procurement supplier sync: %d офферов, ошибок у %d поставщиков%s",
                written,
                len(failed),
                (" (" + ", ".join(map(str, failed)) + ")") if failed else "",
            )
        except Exception as e:
            logger.warning("procurement supplier sync error: %s", e)
            await asyncio.sleep(3600)  # on error retry in 1h


async def procurement_feed_sync() -> None:
    """Суточный разбор YML-фида наличия в 23:40 UTC.

    Строго ПОСЛЕ синка каталога (23:30): фид не создаёт свои строки, а
    проставляет наличие и срок поверх строк сайта, а синк каталога их
    перезаписывает целиком. Обратный порядок означал бы, что пометка живёт
    десять минут и исчезает.

    URL в env `PROCUREMENT_FEED_URL`; не задан — задача молча спит (у
    остальных тенантов фида нет).
    """
    await asyncio.sleep(210)  # warmup, и пропускаем вперёд синк каталога
    while True:
        wait_seconds = _seconds_until(23, 40)
        logger.info("procurement feed sync scheduled in %.1fh", wait_seconds / 3600)
        await asyncio.sleep(wait_seconds)
        try:
            from modules.procurement.feed_adapter import FEED_URL, sync_feed_offers

            if not FEED_URL:
                continue
            stats = await sync_feed_offers()
            logger.info(
                "procurement feed sync: %d позиций, обновлено строк каталога %d, своих %d",
                stats["feed_items"],
                stats["site_rows_updated"],
                stats["own_rows"],
            )
        except Exception as e:
            logger.warning("procurement feed sync error: %s", e)
            await asyncio.sleep(3600)  # on error retry in 1h
