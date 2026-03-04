"""Text message handler — main conversation flow."""

import asyncio
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from ..services.llm_router import get_llm_router
from ..services.session_store import get_session_store
from ..services.stream_renderer import render_stream


router = Router()
logger = logging.getLogger(__name__)

# Per-user locks to serialize requests
_user_locks: dict[int, asyncio.Lock] = {}


def _get_lock(user_id: int) -> asyncio.Lock:
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    return _user_locks[user_id]


@router.message(F.text)
async def on_text_message(message: Message, state: FSMContext) -> None:
    """Forward user text to bridge and stream the response back."""
    if not message.from_user or not message.text:
        return

    user_id = message.from_user.id
    lock = _get_lock(user_id)

    async with lock:
        await _handle_user_message(message, user_id, message.text)


# NOTE: General chat uses Qwen (fast, free)
async def _handle_user_message(
    message: Message, user_id: int, text: str, extra_content: list | None = None
) -> None:
    """Core logic: append user message, call bridge, stream response."""
    store = get_session_store()
    router = get_llm_router()
    session = store.get_or_create(user_id)

    # Build user message content
    if extra_content:
        content = extra_content
    else:
        content = text

    session.append_message("user", content)

    try:
        # Use Qwen via LLM Router for general chat (fast, free)
        stream = router.chat_stream(
            messages=session.messages,
            session_id=session.conversation_id,
            user_id=user_id,
        )

        assistant_text = await render_stream(
            bot=message.bot,
            chat_id=message.chat.id,
            stream=stream,
        )

        session.append_message("assistant", assistant_text)

    except Exception:
        logger.exception("LLM Router request failed for user %s", user_id)
        await message.answer("Произошла ошибка при обработке запроса.")
