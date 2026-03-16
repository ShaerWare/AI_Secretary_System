"""WhatsApp channel startup: auto-start bots."""

import logging

logger = logging.getLogger(__name__)


async def auto_start_bots() -> None:
    """Auto-start WhatsApp bots that have auto_start=True."""
    from db.integration import async_whatsapp_instance_manager
    from whatsapp_manager import whatsapp_manager

    try:
        instances = await async_whatsapp_instance_manager.get_auto_start_instances()
        if not instances:
            logger.info("📱 No WhatsApp bots configured for auto-start")
            return

        started = 0
        for instance in instances:
            instance_id = instance["id"]
            try:
                result = await whatsapp_manager.start_bot(instance_id)
                if result.get("status") in ["started", "already_running"]:
                    started += 1
                    logger.info(f"📱 Auto-started WhatsApp bot: {instance['name']}")
                else:
                    logger.warning(f"📱 Failed to auto-start WhatsApp bot {instance_id}: {result}")
            except Exception as e:
                logger.error(f"📱 Error auto-starting WhatsApp bot {instance_id}: {e}")

        if started > 0:
            logger.info(f"📱 Auto-started {started}/{len(instances)} WhatsApp bots")
    except Exception as e:
        logger.error(f"📱 Error during WhatsApp bot auto-start: {e}")
