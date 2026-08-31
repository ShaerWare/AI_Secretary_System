"""Transport hardening for the Telegram bot session.

Regression cover for the 2026-08-31 outage: the bot polled fine but every reply sat
on a stale pooled connection until aiogram's 60s timeout expired, so the user got a
minute of silence and then an error.
"""

import pytest
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import GetUpdates, SendMessage

from telegram_bot.services import tg_session
from telegram_bot.services.tg_session import (
    KEEPALIVE_TIMEOUT,
    MAX_ATTEMPTS,
    REQUEST_TIMEOUT,
    TunedAiohttpSession,
    retry_on_network_error,
)


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    """Keep the retry tests instant."""
    monkeypatch.setattr(tg_session, "RETRY_DELAY", 0)


def test_session_recycles_idle_connections():
    session = TunedAiohttpSession()

    # Idle connections must be dropped by us before the path drops them silently.
    assert session._connector_init["keepalive_timeout"] == KEEPALIVE_TIMEOUT
    assert session._connector_init["enable_cleanup_closed"] is True
    assert session.timeout == REQUEST_TIMEOUT


async def test_retries_until_the_call_succeeds():
    calls = []

    async def make_request(bot, method):
        calls.append(method)
        if len(calls) < 3:
            raise TelegramNetworkError(method=method, message="Request timeout error")
        return "sent"

    result = await retry_on_network_error(
        make_request, bot=None, method=SendMessage(chat_id=1, text="hi")
    )

    assert result == "sent"
    assert len(calls) == 3


async def test_gives_up_after_max_attempts():
    calls = []

    async def make_request(bot, method):
        calls.append(method)
        raise TelegramNetworkError(method=method, message="Request timeout error")

    with pytest.raises(TelegramNetworkError):
        await retry_on_network_error(
            make_request, bot=None, method=SendMessage(chat_id=1, text="hi")
        )

    assert len(calls) == MAX_ATTEMPTS


async def test_get_updates_is_never_retried():
    """A duplicate poll would earn a Conflict — the dispatcher owns that retry."""
    calls = []

    async def make_request(bot, method):
        calls.append(method)
        raise TelegramNetworkError(method=method, message="Request timeout error")

    with pytest.raises(TelegramNetworkError):
        await retry_on_network_error(make_request, bot=None, method=GetUpdates())

    assert len(calls) == 1


async def test_other_errors_are_not_swallowed():
    async def make_request(bot, method):
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await retry_on_network_error(
            make_request, bot=None, method=SendMessage(chat_id=1, text="hi")
        )
