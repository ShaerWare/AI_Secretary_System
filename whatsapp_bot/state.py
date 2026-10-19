"""Shared bot state — avoids circular imports between bot.py and handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from .config import WhatsAppBotConfig


_bot_config: WhatsAppBotConfig | None = None


def get_bot_config() -> WhatsAppBotConfig | None:
    """Get current bot config (None in standalone mode)."""
    return _bot_config


def set_bot_config(config: WhatsAppBotConfig | None) -> None:
    """Set current bot config."""
    global _bot_config
    _bot_config = config


def sales_funnel_enabled() -> bool:
    """True when this bot may run our own product funnel (pitch, quiz, FAQ).

    The funnel advertises AI Secretary, so it belongs only to our own marketing
    numbers. It used to be hardcoded, which meant a client's assistant answered
    their customers' "привет" with an ad for our product. Multi-instance bots
    now opt in per instance; standalone (`.env`) mode stays on, mirroring the
    Telegram bot — that mode is only ever our own bot.
    """
    config = get_bot_config()
    if config is None:
        return True
    return config.sales_funnel_enabled
