"""Telegram bot handlers."""

import json
import logging
import os
from pathlib import Path

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyKeyboardRemove

from ..services.session_store import get_session_store
from ..state import get_action_buttons
from .callbacks import router as callbacks_router
from .commands import router as commands_router
from .files import router as files_router
from .messages import router as messages_router
from .news import router as news_router
from .sales import get_sales_router
from .tz import router as tz_router


logger = logging.getLogger(__name__)


def _get_welcome_message() -> str:
    """Read welcome_message from bot config file (fallback to generic)."""
    config_file = os.environ.get("BOT_CONFIG_FILE")
    if config_file:
        try:
            data = json.loads(Path(config_file).read_text())
            msg = data.get("welcome_message")
            if msg:
                return msg
        except Exception:
            pass
    return "Здравствуйте! Я AI-ассистент. Напишите мне ваш вопрос."


def _build_url_keyboard() -> InlineKeyboardMarkup | None:
    """Build inline keyboard from action_buttons that have a 'url' field."""
    buttons = get_action_buttons()
    rows = []
    for btn in sorted(buttons, key=lambda b: b.get("order", 99)):
        if not btn.get("enabled", True):
            continue
        url = btn.get("url")
        if not url:
            continue
        icon = btn.get("icon", "")
        label = btn.get("label", url)
        text = f"{icon} {label}" if icon else label
        rows.append([InlineKeyboardButton(text=text, url=url)])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def _make_simple_start_router() -> Router:
    """Create a minimal /start router (no sales funnel)."""
    router = Router()

    @router.message(CommandStart())
    async def cmd_start_simple(message: Message, state: FSMContext) -> None:
        """Handle /start — show welcome message and go straight to AI chat."""
        if not message.from_user:
            return

        # Ensure AI-chat session exists
        store = get_session_store()
        store.get_or_create(message.from_user.id)

        # Clear any leftover FSM state
        await state.clear()

        welcome = _get_welcome_message()
        first_name = message.from_user.first_name
        if first_name:
            welcome = f"{welcome}\n\n{first_name}, напишите ваш вопрос 👇"

        # Remove reply keyboard, show inline URL buttons if configured
        url_kb = _build_url_keyboard()
        await message.answer(
            welcome,
            reply_markup=url_kb or ReplyKeyboardRemove(),
        )

    return router


def get_main_router(skip_sales: bool = False) -> Router:
    """Create and configure the main router with all sub-routers."""
    main_router = Router()
    if skip_sales:
        # Simple /start handler, no sales funnel
        main_router.include_router(_make_simple_start_router())
        logger.info("Sales funnel disabled — using simple /start handler")
    else:
        # Sales funnel first — handles /start, sales: callbacks, FSM text input
        main_router.include_router(get_sales_router())
    # TZ (technical specification) quiz
    main_router.include_router(tz_router)
    # News handler
    main_router.include_router(news_router)
    # AI chat commands (/new, /model) — /start removed, handled by sales
    main_router.include_router(commands_router)
    main_router.include_router(callbacks_router)
    main_router.include_router(files_router)
    # Catch-all MUST be last
    main_router.include_router(messages_router)
    return main_router
