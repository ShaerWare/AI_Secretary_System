"""Tests for long-lived internal bot tokens.

Bot subprocesses receive their internal JWT once, in env, at spawn time and have
no way to refresh it. When that token carried the default 24h admin TTL, every
bot silently started 401ing a day after start — the WhatsApp channel stayed
connected while each incoming message came back as an error.

These tests pin the two properties that keep that from recurring:
- the internal TTL is decoupled from (and far longer than) the admin TTL;
- rotating one bot's token revokes only that bot's previous session, and drops
  it from the session cache — a cached JTI short-circuits DB validation, so a
  token revoked only in the DB would keep working.
"""

from unittest.mock import AsyncMock, patch

import jwt
import pytest

import auth_manager
from auth_manager import (
    BOT_INTERNAL_TOKEN_HOURS,
    JWT_ALGORITHM,
    JWT_EXPIRATION_HOURS,
    JWT_SECRET,
    create_access_token,
    revoke_internal_sessions,
)


def _decode(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


class TestInternalTokenTTL:
    """The internal TTL must outlive a long-running bot subprocess."""

    def test_internal_ttl_far_exceeds_admin_ttl(self):
        # The regression guard: a bot process routinely runs for weeks, so an
        # internal token must not expire on the admin session's schedule.
        assert BOT_INTERNAL_TOKEN_HOURS > JWT_EXPIRATION_HOURS
        assert BOT_INTERNAL_TOKEN_HOURS >= 30 * 24

    def test_expires_hours_override_is_honoured(self):
        _, expires_in, _ = create_access_token(
            "__internal_wa_bot__", "admin", 1, 1, expires_hours=BOT_INTERNAL_TOKEN_HOURS
        )
        assert expires_in == BOT_INTERNAL_TOKEN_HOURS * 3600

    def test_override_reaches_the_encoded_claim(self):
        token, _, _ = create_access_token("__internal_bot__", expires_hours=100)
        payload = _decode(token)
        assert payload["exp"] - payload["iat"] == 100 * 3600

    def test_default_ttl_is_unchanged(self):
        # Human sessions must keep the short admin TTL.
        _, expires_in, _ = create_access_token("admin")
        assert expires_in == JWT_EXPIRATION_HOURS * 3600


class TestInternalSessionRotation:
    """Rotation must be scoped to one bot and must invalidate the cache."""

    @pytest.fixture
    def sessions(self):
        return [
            {"token_jti": "jti-wa-old", "user_agent": "WhatsAppManager:wa-1"},
            {"token_jti": "jti-wa-other", "user_agent": "WhatsAppManager:wa-2"},
            {"token_jti": "jti-browser", "user_agent": "Mozilla/5.0"},
        ]

    async def test_revokes_only_the_matching_user_agent(self, sessions):
        manager = AsyncMock()
        manager.get_active_for_user.return_value = sessions
        manager.revoke_by_user_agent.return_value = 1

        with patch("db.integration.async_session_manager", manager, create=True):
            revoked = await revoke_internal_sessions(1, "WhatsAppManager:wa-1")

        assert revoked == 1
        manager.revoke_by_user_agent.assert_awaited_once_with(1, "WhatsAppManager:wa-1")

    async def test_drops_only_the_matching_jti_from_cache(self, sessions):
        manager = AsyncMock()
        manager.get_active_for_user.return_value = sessions
        manager.revoke_by_user_agent.return_value = 1

        cache = auth_manager._session_cache
        for sess in sessions:
            cache.put(sess["token_jti"], 1)

        with patch("db.integration.async_session_manager", manager, create=True):
            await revoke_internal_sessions(1, "WhatsAppManager:wa-1")

        # The rotated bot's token is gone...
        assert cache.get("jti-wa-old") is None
        # ...while the other bot and the admin's own browser session survive.
        assert cache.get("jti-wa-other") == 1
        assert cache.get("jti-browser") == 1

        cache.remove("jti-wa-other")
        cache.remove("jti-browser")
