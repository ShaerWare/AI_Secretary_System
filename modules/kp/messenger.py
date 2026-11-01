"""КП in the managers' messengers: the card, its buttons and text commands.

The notification about a draft carries the КП itself — what the client asked
for, what the assistant matched, what did not make it in, the text the client
will get — and lets the manager act on it without opening the admin panel:

- Telegram: inline buttons «Отправить / Изменить текст / Отменить» under the
  card; «Изменить» asks for the new text as a reply. When the notification
  token is one of our Telegram bot instances, that bot's process receives the
  presses and forwards them (``telegram_bot/handlers/kp.py`` →
  ``POST /admin/kp/telegram-update``); a dedicated token is long-polled by the
  ``kp-telegram`` task instead.
- WhatsApp: text commands from the staff numbers in ``kp_settings`` —
  «ок 18», «текст 18: …», «отмена 18». The WhatsApp bot hands every incoming
  text to :func:`handle_staff_whatsapp` first; a staff number never reaches
  the assistant, so the director is not answered as a client.

Every action is the same call the admin panel makes (``kp_service.approve`` /
``update_quote`` / ``reject``), so the approval rules stay in one place: a
human still approves every send, only from the messenger.
"""

import asyncio
import logging
import os
import re
from typing import Any, Optional

import httpx


logger = logging.getLogger(__name__)

SUMMARY_PREFIX = "Запрос клиента: "
LINK_LABEL = "[ссылка на КП]"
ACTIONABLE = ("pending", "failed")

TELEGRAM_MAX = 4000
MAX_CARD_ITEMS = 15
POLL_TIMEOUT = 25
CONFLICT_PAUSE = 300

_REF = r"(?:\s*(?:кп|kp))?[\s№#-]*(\d+)?"
_APPROVE_RE = re.compile(
    rf"^\s*(?:ок|ok|окей|отправ\w*|утверд\w*|✅){_REF}\s*[.!]*\s*$", re.IGNORECASE
)
_REJECT_RE = re.compile(rf"^\s*(?:отмен\w*|отклон\w*|❌){_REF}\s*[.!]*\s*$", re.IGNORECASE)
_EDIT_RE = re.compile(
    rf"^\s*(?:текст|измен\w*|✏️?){_REF}\s*[:—-]?\s*(.+)$", re.IGNORECASE | re.DOTALL
)
_LIST_RE = re.compile(r"^\s*(?:кп|kp|список|помощь|help|\?)\s*$", re.IGNORECASE)
# The «Изменить текст» prompt names the quote so the reply can be routed back.
_PROMPT_TAG_RE = re.compile(r"КП #(\d+)")


# ─── Card ─────────────────────────────────────────────────────


def _money(value: Any) -> str:
    from modules.kp.service import _fmt_money

    return _fmt_money(value)


def quote_ref(quote: dict) -> str:
    """Short handle for commands: «КП-0018» → «18»."""
    digits = re.sub(r"\D", "", quote.get("number") or "").lstrip("0")
    return digits or str(quote["id"])


def is_actionable(quote: dict) -> bool:
    return quote.get("status") in ACTIONABLE


def client_text(quote: dict) -> str:
    text = quote.get("message") or (quote.get("outbound_message") or {}).get("text") or ""
    return text.replace("{link}", LINK_LABEL)


def _summary(quote: dict) -> str:
    for event in quote.get("events") or []:
        if event.get("kind") == "info" and (event.get("text") or "").startswith(SUMMARY_PREFIX):
            return event["text"][len(SUMMARY_PREFIX) :].strip()
    return ""


def _delivery_line(quote: dict) -> str:
    delivery = quote.get("delivery")
    if delivery == "whatsapp":
        target = quote.get("target") or ""
        return f"WhatsApp {'+' + target if target.isdigit() else target}"
    if delivery == "email":
        return f"на почту {quote.get('email') or (quote.get('customer') or {}).get('email') or '—'}"
    return "ссылкой — клиенту отправите сами"


def render_card(quote: dict) -> str:
    """The КП as a messenger message: request, matches, gaps, client text."""
    customer = quote.get("customer") or {}
    currency = quote.get("currency") or "₸"
    who = customer.get("name") or "—"
    extra = ", ".join(v for v in (customer.get("contact"), customer.get("phone")) if v)
    valid = quote.get("valid_until") or ""
    if valid:
        y, m, d = (valid.split("-") + ["", ""])[:3]
        valid = f"{d}.{m}.{y}" if d else valid
    lines = [
        f"🧾 {quote.get('number') or 'КП'} — черновик, ждёт подтверждения",
        f"Клиент: {who}{f' ({extra})' if extra else ''}",
        f"Сумма: {_money(quote.get('total'))} {currency}"
        + (f" · действует до {valid}" if valid else ""),
        f"Отправка: {_delivery_line(quote)}",
    ]
    summary = _summary(quote)
    if summary:
        lines += ["", "Что просит клиент:", summary]

    items = quote.get("items") or []
    if items:
        lines += ["", "Что подобрал ассистент:"]
        for i, it in enumerate(items[:MAX_CARD_ITEMS], 1):
            name = it.get("name") or ""
            sku = (it.get("sku") or "").strip()
            if sku and sku not in name:
                name += f" (арт. {sku})"
            count = int(it.get("count") or 1)
            price = float(it.get("price") or 0)
            line = f"{i}. {name} — {count} × {_money(price)} = {_money(price * count)} {currency}"
            if it.get("delivery"):
                line += f", {it['delivery'].lower()}"
            lines.append(line)
            query = (it.get("query") or "").strip()
            if query and query.lower() not in name.lower():
                lines.append(f"   по запросу «{query}»")
        if len(items) > MAX_CARD_ITEMS:
            lines.append(f"… и ещё {len(items) - MAX_CARD_ITEMS} поз. — полный список в CRM → КП")

    flags = quote.get("flags") or []
    if flags:
        lines += ["", "⚠ Не вошло в КП:"] + [f"• {f}" for f in flags]

    text = client_text(quote)
    if text:
        lines += ["", "Текст клиенту:", text]
    if quote.get("status") == "failed" and quote.get("error"):
        lines += ["", f"⚠ Прошлая попытка отправки: {quote['error']}"]
    return "\n".join(lines)


def whatsapp_actions(quote: dict) -> str:
    ref = quote_ref(quote)
    return (
        "Ответьте на это сообщение:\n"
        f"• «ок {ref}» — отправить\n"
        f"• «текст {ref}: новый текст» — заменить текст клиенту\n"
        f"• «отмена {ref}» — не отправлять"
    )


def telegram_keyboard(quote: dict) -> dict:
    qid = quote["id"]
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Отправить", "callback_data": f"kp:approve:{qid}"},
                {"text": "✏️ Изменить текст", "callback_data": f"kp:edit:{qid}"},
            ],
            [{"text": "❌ Отменить", "callback_data": f"kp:reject:{qid}"}],
        ]
    }


# ─── Recipients ───────────────────────────────────────────────


def staff_numbers(settings: dict) -> list[str]:
    from modules.kp.service import _normalize_target

    raw = str(settings.get("notify_whatsapp_numbers") or "")
    return [_normalize_target(n) for n in re.split(r"[,;\n]+", raw) if n.strip()]


def telegram_target(settings: dict) -> tuple[str, str]:
    token = os.getenv("KP_TELEGRAM_BOT_TOKEN") or os.getenv("LEAD_TELEGRAM_BOT_TOKEN", "")
    chat_id = (
        str(settings.get("notify_chat_id") or "").strip()
        or os.getenv("KP_TELEGRAM_CHAT_ID", "")
        or os.getenv("LEAD_TELEGRAM_CHAT_ID", "")
    )
    return token.strip(), chat_id.strip()


# ─── Commands (shared by both messengers) ─────────────────────


def parse_command(text: str) -> Optional[tuple[str, Optional[str], str]]:
    """(action, ref, body) for «ок 18» / «отмена 18» / «текст 18: …» / «кп»."""
    if _LIST_RE.match(text or ""):
        return "list", None, ""
    for action, regex in (("approve", _APPROVE_RE), ("reject", _REJECT_RE)):
        m = regex.match(text or "")
        if m:
            return action, m.group(1), ""
    m = _EDIT_RE.match(text or "")
    if m and m.group(2).strip():
        return "edit", m.group(1), m.group(2).strip()
    return None


async def _open_quotes() -> list[dict]:
    from modules.kp.service import kp_service

    return (await kp_service.list_quotes(status=",".join(ACTIONABLE), limit=200))["quotes"]


async def resolve(ref: Optional[str]) -> tuple[Optional[dict], str]:
    """The quote a command means, or why it can't be told."""
    quotes = await _open_quotes()
    if ref:
        found = [q for q in quotes if quote_ref(q) == ref.lstrip("0")]
        if len(found) == 1:
            return found[0], ""
        if not found:
            return None, f"КП {ref} среди ждущих подтверждения нет — возможно, оно уже обработано."
        return None, f"Под номером {ref} несколько КП — подтвердите в CRM → КП."
    if len(quotes) == 1:
        return quotes[0], ""
    if not quotes:
        return None, "Черновиков КП, ждущих подтверждения, нет."
    return None, "Ждут подтверждения несколько КП — укажите номер:\n" + list_text(quotes)


def list_text(quotes: list[dict]) -> str:
    return "\n".join(
        f"• {quote_ref(q)} — {q.get('number')} «{(q.get('customer') or {}).get('name') or '—'}», "
        f"{_money(q.get('total'))} {q.get('currency') or '₸'}"
        for q in quotes
    )


def _approved_text(quote: dict) -> str:
    number = quote.get("number") or "КП"
    if quote.get("status") in ACTIONABLE or quote.get("status") == "sending":
        return f"⚠ {number} не отправлено: {quote.get('error') or 'неизвестная ошибка'}"
    if quote.get("delivery") == "link":
        return f"✅ {number} опубликовано. Ссылка для клиента: {quote.get('link') or '—'}"
    return f"✅ {number} отправлено клиенту ({_delivery_line(quote)})"


async def approve(quote_id: int, user: str) -> str:
    from modules.kp.service import KpError, kp_service

    try:
        quote = await kp_service.approve(quote_id, user)
    except KpError as e:
        return f"⚠ {e}"
    return _approved_text(quote)


async def reject(quote_id: int, user: str) -> str:
    from modules.kp.service import KpError, kp_service

    try:
        quote = await kp_service.reject(quote_id, user, f"Отменено в мессенджере ({user})")
    except KpError as e:
        return f"⚠ {e}"
    return f"❌ {quote.get('number') or 'КП'} отменено, клиенту ничего не ушло"


async def edit(quote_id: int, text: str, user: str) -> tuple[Optional[dict], str]:
    """Replace the client text; the КП stays a draft until «Отправить»."""
    from modules.kp.service import KpError, kp_service

    message = text.replace(LINK_LABEL, "{link}").strip()
    if not message:
        return None, "⚠ Пустой текст — оставил прежний"
    try:
        quote = await kp_service.update_quote(quote_id, {"message": message}, user)
    except KpError as e:
        return None, f"⚠ {e}"
    await kp_service._event(quote_id, "info", f"Текст клиенту изменён в мессенджере ({user})")
    return quote, "✏️ Текст заменён. КП ещё не отправлено."


# ─── WhatsApp ─────────────────────────────────────────────────


async def handle_staff_whatsapp(sender: str, phone: Optional[str], text: str) -> dict[str, Any]:
    """Called by the WhatsApp bot for every incoming text.

    ``{"handled": False}`` — not a staff number, the assistant answers as usual.
    """
    from modules.kp.service import _normalize_target, kp_service

    settings = await kp_service.get_settings()
    staff = set(staff_numbers(settings))
    who = {_normalize_target(sender), _normalize_target(phone)} - {""}
    if not staff or not (who & staff):
        return {"handled": False}
    user = f"whatsapp:+{_normalize_target(phone) or _normalize_target(sender)}"

    command = parse_command(text)
    if not command:
        quotes = await _open_quotes()
        head = (
            "Этот номер служебный — сообщения с него ассистенту не передаются.\n"
            "Команды: «ок 18», «текст 18: …», «отмена 18», «кп» — список."
        )
        if quotes:
            return {"handled": True, "reply": f"{head}\n\nЖдут подтверждения:\n{list_text(quotes)}"}
        return {"handled": True, "reply": f"{head}\n\nЧерновиков КП, ждущих подтверждения, нет."}

    action, ref, body = command
    if action == "list":
        quotes = await _open_quotes()
        if not quotes:
            return {"handled": True, "reply": "Черновиков КП, ждущих подтверждения, нет."}
        return {"handled": True, "reply": "Ждут подтверждения:\n" + list_text(quotes)}

    quote, error = await resolve(ref)
    if not quote:
        return {"handled": True, "reply": error}
    if action == "approve":
        reply = await approve(quote["id"], user)
    elif action == "reject":
        reply = await reject(quote["id"], user)
    else:
        updated, reply = await edit(quote["id"], body, user)
        if updated:
            reply += f"\n\n{render_card(updated)}\n\n{whatsapp_actions(updated)}"
    logger.info("KP %s via WhatsApp by %s: %s", action, user, reply.splitlines()[0])
    return {"handled": True, "reply": reply}


# ─── Telegram ─────────────────────────────────────────────────


async def telegram_call(token: str, method: str, payload: dict, timeout: float = 15) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"https://api.telegram.org/bot{token}/{method}", json=payload)
    data = resp.json()
    if not data.get("ok"):
        raise TelegramError(resp.status_code, data.get("description") or "")
    return data.get("result") or {}


class TelegramError(Exception):
    def __init__(self, status: int, description: str):
        super().__init__(f"{status}: {description}")
        self.status = status


async def telegram_send(
    token: str,
    chat_id: str,
    text: str,
    keyboard: Optional[dict] = None,
    reply_to: Optional[int] = None,
    force_reply: bool = False,
) -> dict:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text[:TELEGRAM_MAX],
        "disable_web_page_preview": True,
    }
    if keyboard:
        payload["reply_markup"] = keyboard
    elif force_reply:
        payload["reply_markup"] = {"force_reply": True, "selective": True}
    if reply_to:
        payload["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
    return await telegram_call(token, "sendMessage", payload)


def _tg_user(source: dict) -> str:
    user = source.get("from") or {}
    name = user.get("username")
    return f"telegram:@{name}" if name else f"telegram:{user.get('first_name') or user.get('id')}"


async def handle_telegram_update(update: dict, token: str, chat_id: str) -> bool:
    """Act on a button press or a reply. False — not ours, let the bot handle it."""
    from modules.kp.service import kp_service

    if "callback_query" in update:
        cq = update["callback_query"]
        message = cq.get("message") or {}
        if str((message.get("chat") or {}).get("id")) != chat_id:
            return False
        parts = (cq.get("data") or "").split(":")
        if len(parts) != 3 or parts[0] != "kp" or not parts[2].isdigit():
            return False
        action, quote_id, user = parts[1], int(parts[2]), _tg_user(cq)
        await telegram_call(token, "answerCallbackQuery", {"callback_query_id": cq["id"]})
        if action == "edit":
            quote = await kp_service.get_quote(quote_id)
            await telegram_send(
                token,
                chat_id,
                f"✏️ Пришлите ответом на это сообщение новый текст для клиента. "
                f"Ссылку обозначьте {LINK_LABEL} — или я добавлю её в конце.\n\n"
                f"Сейчас:\n{client_text(quote)}\n\nКП #{quote_id}",
                reply_to=message.get("message_id"),
                force_reply=True,
            )
            return True
        if action == "approve":
            reply = await approve(quote_id, user)
        elif action == "reject":
            reply = await reject(quote_id, user)
        else:
            return True
        if not reply.startswith("⚠"):
            try:
                await telegram_call(
                    token,
                    "editMessageReplyMarkup",
                    {"chat_id": chat_id, "message_id": message.get("message_id")},
                )
            except TelegramError:
                pass  # the card is older than 48 h — Telegram no longer lets it change
        await telegram_send(token, chat_id, reply, reply_to=message.get("message_id"))
        logger.info("KP %s #%s via Telegram by %s", action, quote_id, user)
        return True

    message = update.get("message") or {}
    if str((message.get("chat") or {}).get("id")) != chat_id or not message.get("text"):
        return False
    user = _tg_user(message)
    prompt = (message.get("reply_to_message") or {}).get("text") or ""
    tag = _PROMPT_TAG_RE.search(prompt)
    if tag:
        quote, reply = await edit(int(tag.group(1)), message["text"], user)
        await telegram_send(token, chat_id, reply, reply_to=message.get("message_id"))
        if quote:
            await telegram_send(token, chat_id, render_card(quote), telegram_keyboard(quote))
        return True

    # Plain text commands work in Telegram too; any other chatter in the chat is ignored.
    command = parse_command(message["text"])
    if not command:
        return False
    action, ref, body = command
    if action == "list":
        quotes = await _open_quotes()
        await telegram_send(
            token,
            chat_id,
            ("Ждут подтверждения:\n" + list_text(quotes))
            if quotes
            else "Черновиков КП, ждущих подтверждения, нет.",
        )
        return True
    quote, error = await resolve(ref)
    if not quote:
        await telegram_send(token, chat_id, error, reply_to=message.get("message_id"))
        return True
    if action == "approve":
        reply = await approve(quote["id"], user)
    elif action == "reject":
        reply = await reject(quote["id"], user)
    else:
        updated, reply = await edit(quote["id"], body, user)
        if updated:
            await telegram_send(token, chat_id, render_card(updated), telegram_keyboard(updated))
    await telegram_send(token, chat_id, reply, reply_to=message.get("message_id"))
    return True


async def token_runs_as_bot(token: str) -> bool:
    """The notification token belongs to an enabled Telegram bot instance."""
    from sqlalchemy import func, select

    from db.database import AsyncSessionLocal
    from modules.channels.telegram.models import BotInstance

    async with AsyncSessionLocal() as session:
        count = await session.scalar(
            select(func.count(BotInstance.id)).where(
                BotInstance.bot_token == token, BotInstance.enabled.is_(True)
            )
        )
    return bool(count)


_tg_offset: Optional[int] = None


async def telegram_poll_tick() -> None:
    """One long poll of the notification bot (task ``kp-telegram``)."""
    global _tg_offset
    from modules.kp.service import kp_service

    settings = await kp_service.get_settings()
    token, chat_id = telegram_target(settings)
    if not settings["notify_telegram"] or not token or not chat_id:
        await asyncio.sleep(60)
        return
    if await token_runs_as_bot(token):
        # That bot's own process polls it; two pollers knock each other out
        # with 409. Its updates reach us via POST /admin/kp/telegram-update.
        await asyncio.sleep(CONFLICT_PAUSE)
        return
    payload: dict[str, Any] = {
        "timeout": POLL_TIMEOUT,
        "allowed_updates": ["message", "callback_query"],
    }
    if _tg_offset is not None:
        payload["offset"] = _tg_offset
    try:
        updates = await telegram_call(token, "getUpdates", payload, timeout=POLL_TIMEOUT + 10)
    except TelegramError as e:
        # 409: the bot has a webhook or another poller — buttons can't work here.
        logger.warning("KP Telegram polling: %s", e)
        await asyncio.sleep(CONFLICT_PAUSE if e.status == 409 else 30)
        return
    except httpx.HTTPError as e:
        logger.debug("KP Telegram polling: %s", e)
        await asyncio.sleep(10)
        return
    for update in updates or []:
        _tg_offset = int(update["update_id"]) + 1
        try:
            await handle_telegram_update(update, token, chat_id)
        except Exception:
            logger.exception("KP Telegram update %s failed", update.get("update_id"))
