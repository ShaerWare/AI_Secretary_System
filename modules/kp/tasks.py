"""КП background task: pull statuses from the PIM, then run the timers.

Every 10 minutes: offers live 1–3 days, so an hour of lag would eat a real
share of an offer's life. The PIM allows 120 requests a minute; one round is
one list call plus single reads of older open offers (capped).
"""

import logging


logger = logging.getLogger(__name__)

INTERVAL = 10 * 60


async def kp_timers_tick() -> None:
    from modules.kp.pim_client import is_configured
    from modules.kp.service import kp_service

    if not is_configured():
        return
    await kp_service.ensure_default_rules()
    sync = await kp_service.sync_from_pim()
    if not sync.get("ok"):
        logger.warning("KP sync from PIM failed: %s", sync.get("error"))
    stats = await kp_service.run_timers()
    if stats["expired"] or stats["fired"]:
        logger.info("KP timers: %s, sync: %s", stats, sync)
