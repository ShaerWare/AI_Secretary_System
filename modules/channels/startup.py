"""Channel-level startup: bot process watcher + event subscriptions."""

import asyncio
import logging
from collections import defaultdict

from app.dependencies import get_container
from modules.channels.events import BotProcessDied
from modules.monitoring.service import audit_service


logger = logging.getLogger(__name__)

# Restart tracking: {(channel, instance_id): consecutive_failure_count}
_restart_counts: dict[tuple[str, str], int] = defaultdict(int)

_MAX_RESTARTS = 3
_BACKOFF_BASE = 10  # seconds: 10, 20, 30


async def watch_bot_processes() -> None:
    """Detect dead bot processes and publish BotProcessDied events.

    Called periodically by TaskRegistry (every 30s).
    Iterates both Telegram and WhatsApp manager process dicts.
    """
    bus = get_container().event_bus

    dead: list[tuple[str, str, int | None, float]] = []

    # --- Telegram ---
    try:
        from multi_bot_manager import multi_bot_manager

        async with multi_bot_manager._lock:
            to_remove = []
            for iid, proc in multi_bot_manager._processes.items():
                if not proc.is_running:
                    dead.append(("telegram", iid, proc.process.returncode, proc.uptime_seconds))
                    to_remove.append(iid)
            for iid in to_remove:
                del multi_bot_manager._processes[iid]
    except Exception:
        logger.debug("Telegram manager not available", exc_info=True)

    # --- WhatsApp ---
    try:
        from whatsapp_manager import whatsapp_manager

        async with whatsapp_manager._lock:
            to_remove = []
            for iid, proc in whatsapp_manager._processes.items():
                if not proc.is_running:
                    dead.append(("whatsapp", iid, proc.process.returncode, proc.uptime_seconds))
                    to_remove.append(iid)
            for iid in to_remove:
                del whatsapp_manager._processes[iid]
    except Exception:
        logger.debug("WhatsApp manager not available", exc_info=True)

    # Publish events
    for channel, instance_id, exit_code, uptime in dead:
        await bus.publish(
            BotProcessDied(
                channel=channel,
                instance_id=instance_id,
                exit_code=exit_code,
                uptime_seconds=uptime,
            )
        )


async def setup_channel_event_subscriptions(event_bus) -> None:
    """Register event handlers for BotProcessDied."""

    async def on_bot_process_died(event: BotProcessDied) -> None:
        """Audit-log the death and attempt auto-restart with backoff."""
        await _audit_bot_death(event)
        await _auto_restart_bot(event)

    event_bus.subscribe(BotProcessDied, on_bot_process_died)
    logger.info("Channel event subscriptions registered (BotProcessDied)")


async def _audit_bot_death(event: BotProcessDied) -> None:
    """Write bot death to audit log."""
    try:
        exit_label = f"exit_code={event.exit_code}" if event.exit_code is not None else "unknown"
        await audit_service.log(
            action="process_died",
            resource=f"{event.channel}_bot",
            resource_id=str(event.instance_id),
            details={
                "channel": event.channel,
                "exit_code": event.exit_code,
                "uptime_seconds": event.uptime_seconds,
            },
        )
        logger.warning(
            "Bot process died: %s instance=%s %s (uptime=%ds)",
            event.channel,
            event.instance_id,
            exit_label,
            int(event.uptime_seconds),
        )
    except Exception:
        logger.debug("Failed to audit bot death", exc_info=True)


async def _auto_restart_bot(event: BotProcessDied) -> None:
    """Attempt to restart a crashed bot with exponential backoff.

    - exit_code == 0 (graceful stop): no restart
    - Max 3 consecutive restarts; after that, log as failed
    - Backoff: 10s, 20s, 30s
    - Counter resets when uptime exceeds 60s (stable run)
    """
    # Graceful shutdown — do not restart
    if event.exit_code == 0:
        logger.info(
            "Bot %s/%s exited gracefully (code=0), not restarting",
            event.channel,
            event.instance_id,
        )
        return

    key = (event.channel, event.instance_id)

    # Reset counter if the bot had been running stably (>60s)
    if event.uptime_seconds > 60:
        _restart_counts[key] = 0

    count = _restart_counts[key]
    if count >= _MAX_RESTARTS:
        logger.error(
            "Bot %s/%s exceeded max restarts (%d), giving up",
            event.channel,
            event.instance_id,
            _MAX_RESTARTS,
        )
        try:
            await audit_service.log(
                action="restart_failed",
                resource=f"{event.channel}_bot",
                resource_id=str(event.instance_id),
                details={"reason": f"exceeded {_MAX_RESTARTS} consecutive restarts"},
            )
        except Exception:
            pass
        return

    delay = _BACKOFF_BASE * (count + 1)
    _restart_counts[key] = count + 1

    logger.info(
        "Auto-restarting %s/%s in %ds (attempt %d/%d)",
        event.channel,
        event.instance_id,
        delay,
        count + 1,
        _MAX_RESTARTS,
    )

    await asyncio.sleep(delay)

    try:
        if event.channel == "telegram":
            from multi_bot_manager import multi_bot_manager

            result = await multi_bot_manager.start_bot(event.instance_id)
        else:
            from whatsapp_manager import whatsapp_manager

            result = await whatsapp_manager.start_bot(event.instance_id)

        if result.get("status") == "running":
            logger.info(
                "Auto-restart succeeded: %s/%s (attempt %d)",
                event.channel,
                event.instance_id,
                count + 1,
            )
        else:
            logger.warning(
                "Auto-restart returned non-running status: %s/%s: %s",
                event.channel,
                event.instance_id,
                result,
            )
    except Exception:
        logger.error(
            "Auto-restart failed: %s/%s",
            event.channel,
            event.instance_id,
            exc_info=True,
        )
