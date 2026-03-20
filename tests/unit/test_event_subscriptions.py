"""Tests for event subscription wiring (setup_event_subscriptions)."""

from unittest.mock import AsyncMock, MagicMock, patch

from modules.core.events import EventBus, SessionRevoked, UserRoleChanged
from modules.core.startup import setup_event_subscriptions


async def test_user_role_changed_revokes_sessions_and_invalidates_cache():
    bus = EventBus()
    await setup_event_subscriptions(bus)

    mock_cache = MagicMock()
    mock_revoke = AsyncMock(return_value=1)

    with (
        patch("auth_manager._member_role_cache", mock_cache),
        patch("auth_manager.revoke_all_user_sessions", mock_revoke),
    ):
        await bus.publish(
            UserRoleChanged(user_id=5, workspace_id=1, old_role="viewer", new_role="admin")
        )

    mock_cache.invalidate_user.assert_called_once_with(5)
    mock_revoke.assert_awaited_once_with(5)


async def test_session_revoked_revokes_sessions_and_invalidates_cache():
    bus = EventBus()
    await setup_event_subscriptions(bus)

    mock_cache = MagicMock()
    mock_revoke = AsyncMock(return_value=1)

    with (
        patch("auth_manager._member_role_cache", mock_cache),
        patch("auth_manager.revoke_all_user_sessions", mock_revoke),
    ):
        await bus.publish(SessionRevoked(user_id=10, reason="password_changed"))

    mock_cache.invalidate_user.assert_called_once_with(10)
    mock_revoke.assert_awaited_once_with(10)


async def test_handler_error_does_not_propagate():
    """Event handler exceptions should be logged, not raised."""
    bus = EventBus()
    await setup_event_subscriptions(bus)

    mock_revoke = AsyncMock(side_effect=RuntimeError("db gone"))

    with (
        patch("auth_manager._member_role_cache", MagicMock()),
        patch("auth_manager.revoke_all_user_sessions", mock_revoke),
    ):
        # Should not raise
        await bus.publish(SessionRevoked(user_id=99, reason="deactivated"))
