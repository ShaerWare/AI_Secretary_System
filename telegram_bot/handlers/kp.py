"""КП buttons and replies under the managers' notifications.

When this bot is also the КП notification bot (``LEAD_TELEGRAM_BOT_TOKEN``),
Telegram delivers the presses on those cards here — the orchestrator cannot
poll the same token without knocking this process off with 409. The bot
forwards them to ``POST /admin/kp/telegram-update``; the orchestrator owns the
chat check and the actions (``modules/kp/messenger.py``) and answers itself.
"""

import logging
import re

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import CallbackQuery, Message

from ..services.llm_router import get_llm_router


router = Router()
logger = logging.getLogger(__name__)

# Same shapes as modules/kp/messenger: «ок 18» / «отмена 18» / «текст 18: …» / «кп»,
# and replies to the «Изменить текст» prompt («… КП #21»).
_COMMAND_RE = re.compile(
    r"^\s*(?:ок|ok|окей|отправ\w*|утверд\w*|отмен\w*|отклон\w*|текст|измен\w*|кп|kp|список)\b",
    re.IGNORECASE,
)
_PROMPT_TAG_RE = re.compile(r"КП #\d+")
TIMEOUT = 90


def _user(user) -> dict:
    return {"id": user.id, "username": user.username, "first_name": user.first_name}


async def _forward(update: dict) -> bool:
    router_ = get_llm_router()
    try:
        client = await router_._get_client()
        resp = await client.post(
            f"{router_.orchestrator_url}/admin/kp/telegram-update",
            json={"update": update},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return bool(resp.json().get("handled"))
    except Exception as e:
        logger.warning("KP update forward failed: %s", e)
        return False


@router.callback_query(F.data.startswith("kp:"))
async def on_kp_button(callback: CallbackQuery) -> None:
    message = callback.message
    if not message or not callback.from_user:
        return
    handled = await _forward(
        {
            "callback_query": {
                "id": callback.id,
                "from": _user(callback.from_user),
                "data": callback.data,
                "message": {"message_id": message.message_id, "chat": {"id": message.chat.id}},
            }
        }
    )
    if not handled:
        await callback.answer("Недоступно", show_alert=False)


def _maybe_kp(message: Message) -> bool:
    if not message.text:
        return False
    reply = message.reply_to_message
    if reply and reply.text and _PROMPT_TAG_RE.search(reply.text):
        return True
    return bool(_COMMAND_RE.match(message.text))


@router.message(F.text, _maybe_kp)
async def on_kp_text(message: Message) -> None:
    reply = message.reply_to_message
    update = {
        "message": {
            "message_id": message.message_id,
            "chat": {"id": message.chat.id},
            "from": _user(message.from_user) if message.from_user else {},
            "text": message.text,
        }
    }
    if reply and reply.text:
        update["message"]["reply_to_message"] = {"text": reply.text}
    if not await _forward(update):
        # Not the notification chat or not a command — a client's «ок» goes on to the chat.
        raise SkipHandler
