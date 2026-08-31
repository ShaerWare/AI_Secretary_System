"""HTTP session for the Telegram API, tuned for long-lived bot processes.

aiogram's stock session keeps pooled TLS connections to api.telegram.org for as long
as aiohttp will let it and waits out a 60s request timeout on every one of them. The
polling connection is in constant use and stays healthy, but the connection used for
*replies* sits idle between messages — and an idle connection here gets dropped
somewhere on the path without a FIN. The first reply after a pause then hung for the
full 60 seconds and the user got "Произошла ошибка" instead of an answer, while the
retry issued straight after went through in 76 ms (2026-08-31, @stalkerelectricbot).

Two defences:

* recycle idle connections faster than they can go stale (``keepalive_timeout``), which
  removes the cause;
* retry a request that died on the network instead of surrendering the turn, which
  covers the blips that remain.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import GetUpdates


if TYPE_CHECKING:
    from aiogram.client.session.middlewares.base import NextRequestMiddlewareType
    from aiogram.methods import Response, TelegramMethod
    from aiogram.methods.base import TelegramType


logger = logging.getLogger(__name__)

# Per-request ceiling. The dispatcher asks for `timeout + polling_timeout` on
# getUpdates, so long polling is unaffected by lowering this.
REQUEST_TIMEOUT = 20.0

# Must stay below the shortest idle timeout on the path to Telegram. 25s is well
# under the usual 60-120s NAT/conntrack window, so we close the connection first.
KEEPALIVE_TIMEOUT = 25.0

MAX_ATTEMPTS = 3
RETRY_DELAY = 0.5


class TunedAiohttpSession(AiohttpSession):
    """aiogram session that lets idle connections die before the network kills them."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        super().__init__(**kwargs)
        # `_connector_init` is the kwargs dict aiogram hands to TCPConnector when it
        # lazily builds the aiohttp session. These two knobs have no public setter,
        # so extending that dict is the supported-in-practice way to reach them.
        self._connector_init.update(
            keepalive_timeout=KEEPALIVE_TIMEOUT,
            enable_cleanup_closed=True,
        )


async def retry_on_network_error(
    make_request: NextRequestMiddlewareType[TelegramType],
    bot: Bot,
    method: TelegramMethod[TelegramType],
) -> Response[TelegramType]:
    """Retry an API call that failed at the network layer.

    getUpdates is exempt: the dispatcher runs its own reconnect loop and a duplicate
    poll would earn a ``Conflict: terminated by other getUpdates request``.

    A retried send can in principle duplicate a message that did reach Telegram but
    whose response was lost. That is the deliberate trade: a stray duplicate is a far
    better outcome for the user than a minute of silence followed by an error.
    """
    if isinstance(method, GetUpdates):
        return await make_request(bot, method)

    last_error: TelegramNetworkError | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return await make_request(bot, method)
        except TelegramNetworkError as e:
            last_error = e
            if attempt == MAX_ATTEMPTS:
                break
            logger.warning(
                "%s failed on the network (attempt %s/%s): %s — retrying",
                type(method).__name__,
                attempt,
                MAX_ATTEMPTS,
                e,
            )
            await asyncio.sleep(RETRY_DELAY * attempt)

    assert last_error is not None
    logger.error(
        "%s failed on the network after %s attempts: %s",
        type(method).__name__,
        MAX_ATTEMPTS,
        last_error,
    )
    raise last_error


def build_bot(token: str, **kwargs: Any) -> Bot:
    """Build a Bot whose transport survives idle periods and transient network faults."""
    bot = Bot(token=token, session=TunedAiohttpSession(), **kwargs)
    bot.session.middleware(retry_on_network_error)
    return bot
