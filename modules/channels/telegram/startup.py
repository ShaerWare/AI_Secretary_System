"""Telegram channel startup: auto-start bots."""

import logging


logger = logging.getLogger(__name__)


async def auto_start_bots() -> None:
    """Auto-start Telegram bots that have auto_start=True."""
    from db.integration import async_bot_instance_manager
    from multi_bot_manager import multi_bot_manager

    try:
        instances = await async_bot_instance_manager.get_auto_start_instances()
        if not instances:
            logger.info("📱 No Telegram bots configured for auto-start")
            return

        started = 0
        for instance in instances:
            instance_id = instance["id"]
            try:
                result = await multi_bot_manager.start_bot(instance_id)
                if result.get("status") in ["started", "already_running"]:
                    started += 1
                    logger.info(f"📱 Auto-started Telegram bot: {instance['name']}")
                else:
                    logger.warning(f"📱 Failed to auto-start bot {instance_id}: {result}")
            except Exception as e:
                logger.error(f"📱 Error auto-starting bot {instance_id}: {e}")

        if started > 0:
            logger.info(f"📱 Auto-started {started}/{len(instances)} Telegram bots")
    except Exception as e:
        logger.error(f"📱 Error during Telegram bot auto-start: {e}")
