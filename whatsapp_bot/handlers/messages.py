"""Text message handler — main conversation flow for WhatsApp.

Receives text from webhook, routes through LLM, sends response back.
Unlike Telegram, WhatsApp doesn't support message editing, so we collect
the full response before sending (no streaming to user).
"""

import asyncio
import logging

from ..services.llm_router import get_llm_router
from ..services.outbound import submit_reply
from ..services.session_store import get_session_store
from ..services.whatsapp_client import get_whatsapp_client, split_text
from ..state import sales_funnel_enabled


logger = logging.getLogger(__name__)

# Per-user locks to serialize requests
_user_locks: dict[str, asyncio.Lock] = {}


def _get_lock(phone: str) -> asyncio.Lock:
    if phone not in _user_locks:
        _user_locks[phone] = asyncio.Lock()
    return _user_locks[phone]


async def handle_text_message(phone: str, text: str, message_id: str) -> None:
    """Handle an incoming text message from WhatsApp.

    Args:
        phone: Sender phone number (E.164 without +)
        text: Message text content
        message_id: WhatsApp message ID (wamid)
    """
    lock = _get_lock(phone)

    async with lock:
        # Track WhatsApp contact as user identity
        try:
            from db.integration import async_user_identity_manager

            await async_user_identity_manager.find_or_create(
                provider="whatsapp",
                provider_uid=phone,
                display_name=phone,
            )
        except Exception:
            logger.debug("Failed to track WhatsApp identity for %s", phone, exc_info=True)

        await _process_message(phone, text, message_id)


async def _process_message(phone: str, text: str, message_id: str) -> None:
    """Core logic: mark as read, call LLM, send response."""
    wa_client = get_whatsapp_client()

    # Mark as read (blue checkmarks). Synthetic calls (a stale menu tap routed
    # here as text) carry no message id — nothing to acknowledge.
    if message_id:
        try:
            await wa_client.mark_as_read(message_id)
        except Exception:
            logger.debug("Failed to mark message as read", exc_info=True)

    # Our own product funnel (pitch + quiz + platform FAQ) — only for our
    # marketing numbers. A client's assistant must answer "привет" itself,
    # not with an ad for AI Secretary.
    if sales_funnel_enabled():
        # Greeting detection — send welcome with quick-reply buttons
        _GREETINGS = {
            "/start",
            "/menu",
            "start",
            "menu",
            "привет",
            "здравствуйте",
            "хай",
            "hello",
            "hi",
        }
        lower = text.lower().strip()
        if lower in _GREETINGS:
            from .sales.welcome import handle_welcome

            await handle_welcome(phone)
            return

        # State-aware routing: check if user is in a free-text input state
        from ..sales.database import get_sales_db

        try:
            db = await get_sales_db()
            state = await db.get_user_state(phone)
            if state:
                if state == "custom_step_1":
                    from .sales.custom import handle_custom_step_1_text

                    await handle_custom_step_1_text(phone, text)
                    return
                elif state == "diy_gpu_custom":
                    from .sales.diy import handle_gpu_custom_text

                    await handle_gpu_custom_text(phone, text)
                    return
        except Exception:
            logger.debug("Sales DB state check failed", exc_info=True)

    store = get_session_store()
    router = get_llm_router()

    session = store.get_or_create(phone)
    session.append_message("user", text)

    try:
        # Non-streaming: collect full response (WhatsApp can't edit messages)
        # The phone keys the orchestrator session, so the conversation keeps
        # its history instead of starting over on every message.
        response = await router.chat(messages=session.messages, conversation_key=phone)
        session.append_message("assistant", response)

        # Approval mode: the reply waits in the outbound queue and the client
        # only gets the fixed acknowledgement (if any).
        decision = await submit_reply(router, phone, text, response)
        if decision.get("action") == "send":
            outgoing = response
        else:
            outgoing = decision.get("ack_text") or ""

        # Split long responses into multiple messages
        for chunk in split_text(outgoing) if outgoing else []:
            await wa_client.send_text(to=phone, text=chunk)

    except Exception:
        logger.exception("LLM request failed for phone %s", phone)
        await wa_client.send_text(
            to=phone,
            text="Произошла ошибка при обработке запроса. Попробуйте позже.",
        )
