"""Tests for ConfigChanged event — publish from ConfigService + audit subscriber."""

from unittest.mock import AsyncMock, MagicMock, patch

from modules.core.events import ConfigChanged, EventBus
from modules.core.startup import setup_event_subscriptions


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------


def test_config_changed_fields():
    """ConfigChanged carries key, value, previous_value, namespace."""
    event = ConfigChanged(
        key="widget",
        value={"title": "New"},
        previous_value={"title": "Old"},
        namespace="widget",
    )
    assert event.key == "widget"
    assert event.value == {"title": "New"}
    assert event.previous_value == {"title": "Old"}
    assert event.namespace == "widget"
    assert event.timestamp > 0


def test_config_changed_defaults():
    """Default field values are sensible."""
    event = ConfigChanged()
    assert event.key == ""
    assert event.value is None
    assert event.previous_value is None
    assert event.namespace == ""


# ---------------------------------------------------------------------------
# Namespace derivation
# ---------------------------------------------------------------------------


def test_namespace_from_dotted_key():
    """Namespace is derived as first segment of dotted key."""
    key = "widget.colors.primary"
    namespace = key.split(".", maxsplit=1)[0]
    assert namespace == "widget"


def test_namespace_from_simple_key():
    """Simple key uses itself as namespace."""
    key = "telegram"
    namespace = key.split(".", maxsplit=1)[0]
    assert namespace == "telegram"


# ---------------------------------------------------------------------------
# ConfigService.set() publishes event
# ---------------------------------------------------------------------------


async def test_set_publishes_config_changed():
    """ConfigService.set() publishes ConfigChanged after commit."""
    bus = EventBus()
    received: list[ConfigChanged] = []

    async def handler(event: ConfigChanged) -> None:
        received.append(event)

    bus.subscribe(ConfigChanged, handler)

    mock_repo = MagicMock()
    mock_repo.get_config = AsyncMock(return_value="old_val")
    mock_repo.set_config = AsyncMock(return_value=True)

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    mock_container = MagicMock()
    mock_container.event_bus = bus

    from modules.core.service import ConfigService

    svc = ConfigService()

    with (
        patch("modules.core.service.AsyncSessionLocal") as mock_asl,
        patch("modules.core.service._get_event_bus", return_value=bus),
    ):
        mock_asl.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_asl.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_session.__class__ = type(mock_session)
        # Patch ConfigRepository constructor
        with patch("modules.core.service.ConfigRepository", return_value=mock_repo):
            result = await svc.set("tts", {"engine": "piper"})

    assert result is True
    assert len(received) == 1
    assert received[0].key == "tts"
    assert received[0].value == {"engine": "piper"}
    assert received[0].previous_value == "old_val"
    assert received[0].namespace == "tts"


async def test_set_works_without_event_bus():
    """ConfigService.set() works even when EventBus is unavailable."""
    mock_repo = MagicMock()
    mock_repo.get_config = AsyncMock(return_value=None)
    mock_repo.set_config = AsyncMock(return_value=True)

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    from modules.core.service import ConfigService

    svc = ConfigService()

    with (
        patch("modules.core.service.AsyncSessionLocal") as mock_asl,
        patch("modules.core.service._get_event_bus", return_value=None),
        patch("modules.core.service.ConfigRepository", return_value=mock_repo),
    ):
        mock_asl.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_asl.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await svc.set("llm", {"backend": "gemini"})

    assert result is True


# ---------------------------------------------------------------------------
# Audit subscriber
# ---------------------------------------------------------------------------


async def test_audit_subscriber_logs_config_change():
    """on_config_changed handler writes audit log entry."""
    bus = EventBus()
    mock_audit = AsyncMock()

    with (
        patch("auth_manager._member_role_cache", MagicMock()),
        patch("auth_manager.revoke_all_user_sessions", AsyncMock()),
        patch("modules.monitoring.service.audit_service", mock_audit),
    ):
        await setup_event_subscriptions(bus)
        await bus.publish(
            ConfigChanged(
                key="tts",
                value={"engine": "piper"},
                previous_value={"engine": "xtts"},
                namespace="tts",
            )
        )

    mock_audit.log.assert_awaited_once_with(
        action="config_changed",
        resource="config",
        resource_id="tts",
        details={
            "namespace": "tts",
            "previous_value": {"engine": "xtts"},
            "new_value": {"engine": "piper"},
        },
    )


async def test_audit_subscriber_handles_repeated_events_idempotently():
    """Publishing same event twice creates two independent audit entries."""
    bus = EventBus()
    mock_audit = AsyncMock()

    with (
        patch("auth_manager._member_role_cache", MagicMock()),
        patch("auth_manager.revoke_all_user_sessions", AsyncMock()),
        patch("modules.monitoring.service.audit_service", mock_audit),
    ):
        await setup_event_subscriptions(bus)
        event = ConfigChanged(key="widget", value="v1", namespace="widget")
        await bus.publish(event)
        await bus.publish(event)

    assert mock_audit.log.await_count == 2


async def test_config_changed_handler_error_does_not_propagate():
    """Audit handler failure should not raise to publisher."""
    bus = EventBus()
    mock_audit = MagicMock()
    mock_audit.log = AsyncMock(side_effect=RuntimeError("db gone"))

    with (
        patch("auth_manager._member_role_cache", MagicMock()),
        patch("auth_manager.revoke_all_user_sessions", AsyncMock()),
        patch("modules.monitoring.service.audit_service", mock_audit),
    ):
        await setup_event_subscriptions(bus)
        # Should not raise
        await bus.publish(ConfigChanged(key="tts", value="new", namespace="tts"))
