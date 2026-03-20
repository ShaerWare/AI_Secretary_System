"""Tests for BotProcessDied event: watcher, audit, auto-restart."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from modules.channels.events import BotProcessDied
from modules.channels.startup import (
    _MAX_RESTARTS,
    _audit_bot_death,
    _auto_restart_bot,
    _restart_counts,
    setup_channel_event_subscriptions,
    watch_bot_processes,
)
from modules.core.events import EventBus


def _make_proc(instance_id, *, running, returncode=1, uptime=120):
    """Create a mock bot process object."""
    proc = MagicMock()
    proc.instance_id = instance_id
    proc.is_running = running
    proc.uptime_seconds = uptime
    proc.process = MagicMock()
    proc.process.returncode = returncode
    return proc


def _mock_manager(processes=None):
    """Create a mock bot manager with lock and processes dict."""
    mgr = MagicMock()
    mgr._lock = asyncio.Lock()
    mgr._processes = dict(processes or {})
    return mgr


async def test_watcher_detects_dead_telegram_bot():
    """Watcher publishes BotProcessDied for a dead Telegram process."""
    dead_proc = _make_proc("42", running=False, returncode=1, uptime=300)
    tg_mgr = _mock_manager({"42": dead_proc})
    wa_mgr = _mock_manager()

    events = []
    bus = EventBus()

    async def capture(e):
        events.append(e)

    bus.subscribe(BotProcessDied, capture)

    with (
        patch(
            "modules.channels.startup.get_container",
            return_value=MagicMock(event_bus=bus),
        ),
        patch.dict(
            "sys.modules",
            {
                "multi_bot_manager": MagicMock(multi_bot_manager=tg_mgr),
                "whatsapp_manager": MagicMock(whatsapp_manager=wa_mgr),
            },
        ),
    ):
        await watch_bot_processes()

    assert len(events) == 1
    assert events[0].channel == "telegram"
    assert events[0].instance_id == "42"
    assert events[0].exit_code == 1
    assert events[0].uptime_seconds == 300
    assert "42" not in tg_mgr._processes


async def test_watcher_detects_dead_whatsapp_bot():
    """Watcher publishes BotProcessDied for a dead WhatsApp process."""
    dead_proc = _make_proc("7", running=False, returncode=137, uptime=60)
    tg_mgr = _mock_manager()
    wa_mgr = _mock_manager({"7": dead_proc})

    events = []
    bus = EventBus()

    async def capture(e):
        events.append(e)

    bus.subscribe(BotProcessDied, capture)

    with (
        patch(
            "modules.channels.startup.get_container",
            return_value=MagicMock(event_bus=bus),
        ),
        patch.dict(
            "sys.modules",
            {
                "multi_bot_manager": MagicMock(multi_bot_manager=tg_mgr),
                "whatsapp_manager": MagicMock(whatsapp_manager=wa_mgr),
            },
        ),
    ):
        await watch_bot_processes()

    assert len(events) == 1
    assert events[0].channel == "whatsapp"
    assert events[0].exit_code == 137


async def test_watcher_ignores_running_processes():
    """Watcher does not publish events for running processes."""
    running_proc = _make_proc("1", running=True)
    tg_mgr = _mock_manager({"1": running_proc})
    wa_mgr = _mock_manager()

    events = []
    bus = EventBus()

    async def capture(e):
        events.append(e)

    bus.subscribe(BotProcessDied, capture)

    with (
        patch(
            "modules.channels.startup.get_container",
            return_value=MagicMock(event_bus=bus),
        ),
        patch.dict(
            "sys.modules",
            {
                "multi_bot_manager": MagicMock(multi_bot_manager=tg_mgr),
                "whatsapp_manager": MagicMock(whatsapp_manager=wa_mgr),
            },
        ),
    ):
        await watch_bot_processes()

    assert len(events) == 0
    assert "1" in tg_mgr._processes


async def test_audit_bot_death():
    """Audit handler logs bot death."""
    event = BotProcessDied(channel="telegram", instance_id="42", exit_code=1, uptime_seconds=300)

    mock_audit = AsyncMock()
    with patch("modules.channels.startup.audit_service", mock_audit):
        await _audit_bot_death(event)

    mock_audit.log.assert_awaited_once()
    kw = mock_audit.log.call_args[1]
    assert kw["action"] == "process_died"
    assert kw["resource"] == "telegram_bot"
    assert kw["resource_id"] == "42"


async def test_auto_restart_skips_graceful_exit():
    """Auto-restart does nothing when exit_code is 0."""
    event = BotProcessDied(channel="telegram", instance_id="99", exit_code=0, uptime_seconds=600)

    mock_mgr = MagicMock()
    mock_mgr.start_bot = AsyncMock()
    _restart_counts.clear()

    with patch.dict(
        "sys.modules",
        {"multi_bot_manager": MagicMock(multi_bot_manager=mock_mgr)},
    ):
        await _auto_restart_bot(event)

    mock_mgr.start_bot.assert_not_awaited()


async def test_auto_restart_with_backoff():
    """Auto-restart calls start_bot after backoff delay."""
    event = BotProcessDied(channel="telegram", instance_id="10", exit_code=1, uptime_seconds=5)

    mock_mgr = MagicMock()
    mock_mgr.start_bot = AsyncMock(return_value={"status": "running"})
    _restart_counts.clear()

    with (
        patch.dict(
            "sys.modules",
            {"multi_bot_manager": MagicMock(multi_bot_manager=mock_mgr)},
        ),
        patch("modules.channels.startup.asyncio") as mock_asyncio,
    ):
        mock_asyncio.sleep = AsyncMock()
        await _auto_restart_bot(event)

    mock_asyncio.sleep.assert_awaited_once_with(10)  # first attempt: 10s
    mock_mgr.start_bot.assert_awaited_once_with("10")


async def test_auto_restart_gives_up_after_max():
    """Auto-restart stops after MAX_RESTARTS consecutive failures."""
    event = BotProcessDied(channel="whatsapp", instance_id="5", exit_code=1, uptime_seconds=3)

    mock_mgr = MagicMock()
    mock_mgr.start_bot = AsyncMock()
    _restart_counts.clear()
    _restart_counts[("whatsapp", "5")] = _MAX_RESTARTS

    with (
        patch.dict(
            "sys.modules",
            {"whatsapp_manager": MagicMock(whatsapp_manager=mock_mgr)},
        ),
        patch("modules.channels.startup.audit_service", AsyncMock()),
    ):
        await _auto_restart_bot(event)

    mock_mgr.start_bot.assert_not_awaited()


async def test_restart_counter_resets_on_stable_run():
    """Restart counter resets when uptime > 60s (stable run)."""
    event = BotProcessDied(channel="telegram", instance_id="10", exit_code=1, uptime_seconds=120)

    mock_mgr = MagicMock()
    mock_mgr.start_bot = AsyncMock(return_value={"status": "running"})
    _restart_counts.clear()
    _restart_counts[("telegram", "10")] = 2

    with (
        patch.dict(
            "sys.modules",
            {"multi_bot_manager": MagicMock(multi_bot_manager=mock_mgr)},
        ),
        patch("modules.channels.startup.asyncio") as mock_asyncio,
    ):
        mock_asyncio.sleep = AsyncMock()
        await _auto_restart_bot(event)

    # Counter reset to 0 because uptime > 60, so delay = 10 * (0 + 1) = 10
    mock_asyncio.sleep.assert_awaited_once_with(10)
    mock_mgr.start_bot.assert_awaited_once_with("10")


async def test_event_subscription_wiring():
    """setup_channel_event_subscriptions registers BotProcessDied handler."""
    bus = EventBus()
    await setup_channel_event_subscriptions(bus)

    assert BotProcessDied in bus._handlers
    assert len(bus._handlers[BotProcessDied]) == 1


async def test_bot_process_died_event_fields():
    """BotProcessDied has expected fields."""
    event = BotProcessDied(channel="telegram", instance_id="42", exit_code=1, uptime_seconds=300.5)
    assert event.channel == "telegram"
    assert event.instance_id == "42"
    assert event.exit_code == 1
    assert event.uptime_seconds == 300.5
    assert event.timestamp > 0
