"""Telegram bot entry point.

Run with:  python -m telegram_bot
"""

import asyncio
import logging
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from .config import (
    BotConfig,
    get_bot_instance_id,
    get_telegram_settings,
    load_config_from_api,
)
from .handlers import get_main_router
from .middleware.access import AccessMiddleware
from .sales.database import get_sales_db
from .sales.keyboards import DEFAULT_ACTION_BUTTONS
from .services.github_news import news_broadcast_scheduler
from .services.llm_router import get_llm_router


logger = logging.getLogger(__name__)

# Global bot config (available to handlers)
_bot_config: BotConfig | None = None
_action_buttons: list[dict[str, Any]] = DEFAULT_ACTION_BUTTONS


def get_bot_config() -> BotConfig | None:
    """Get current bot config (None in standalone mode)."""
    return _bot_config


def get_action_buttons() -> list[dict[str, Any]]:
    """Get current action buttons config."""
    return _action_buttons


async def main() -> None:
    global _bot_config, _action_buttons

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Check for multi-instance mode
    instance_id = get_bot_instance_id()

    if instance_id:
        # Multi-instance mode: load config from orchestrator API
        logger.info(f"Multi-instance mode: loading config for {instance_id}")
        try:
            _bot_config = await load_config_from_api(instance_id)
            bot_token = _bot_config.bot_token
            _action_buttons = _bot_config.action_buttons or DEFAULT_ACTION_BUTTONS
            logger.info(f"Loaded config for bot: {_bot_config.name}")
            logger.info(f"LLM backend: {_bot_config.llm_backend}")
            logger.info(f"Action buttons: {len(_action_buttons)} configured")
        except Exception as e:
            logger.error(f"Failed to load config from API: {e}")
            logger.info("Falling back to .env configuration")
            settings = get_telegram_settings()
            bot_token = settings.bot_token
    else:
        # Standalone mode: use .env settings
        logger.info("Standalone mode: using .env configuration")
        settings = get_telegram_settings()
        bot_token = settings.bot_token

    bot = Bot(token=bot_token)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Register access middleware on all update types
    dp.message.middleware(AccessMiddleware())
    dp.callback_query.middleware(AccessMiddleware())

    # Initialize sales database
    db = await get_sales_db()
    logger.info("Sales DB initialized")

    # Register routers (pass action_buttons for keyboard building)
    dp.include_router(get_main_router())

    logger.info("Starting Telegram bot (polling)…")

    if _bot_config:
        logger.info(f"Bot name: {_bot_config.name}")
        logger.info(f"Instance ID: {_bot_config.instance_id}")
    else:
        settings = get_telegram_settings()
        logger.info(f"Bridge URL: {settings.bridge_url}")
        allowed = settings.get_allowed_user_ids()
        if allowed:
            logger.info(f"Allowed users: {allowed}")

    # Start news broadcast scheduler (checks every hour)
    scheduler_task = asyncio.create_task(news_broadcast_scheduler(bot, interval_hours=1))
    logger.info("News broadcast scheduler started")

    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "pre_checkout_query"],
        )
    finally:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        router = get_llm_router()
        await router.close()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


def run() -> None:
    """Entry point for ``python -m src.telegram.bot``."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
