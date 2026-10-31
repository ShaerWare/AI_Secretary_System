"""КП workflow: draft in the PIM → human approval → delivery → timers.

Rules this module enforces:
- The assistant only ever creates DRAFTS. Nothing reaches the client before a
  manager or the director approves it (MASTER WORKFLOW: КП — черновик на директора).
- WhatsApp delivery goes through the existing outbound approval queue: the КП
  shows up there and on the КП tab, and approving in either place is the same
  action (:meth:`KpService.approve` → ``outbound_service.approve``).
- An expired offer is never sent or prolonged at old prices silently: it has to
  be reissued, which recalculates nothing by itself but makes a human look again.
- Messages to the client produced by timers also wait in the approval queue.
"""

import logging
import os
import re
from datetime import date, datetime, timedelta
from typing import Any, Optional

import httpx
from sqlalchemy import func, select

from db.database import AsyncSessionLocal
from db.retry import retry_on_busy
from modules.core.service import config_service
from modules.kp import timers
from modules.kp.models import (
    ACTION_CLIENT_MESSAGE,
    ACTION_MARK_LOST,
    ACTION_NOTIFY,
    ACTIONS,
    DELIVERY_EMAIL,
    DELIVERY_LINK,
    DELIVERY_MODES,
    DELIVERY_WHATSAPP,
    OPEN_STATUSES,
    ORIGIN_ASSISTANT,
    ORIGIN_MANUAL,
    ORIGIN_PIM,
    STATUS_ACCEPTED,
    STATUS_CLARIFICATION,
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_LOST,
    STATUS_PENDING,
    STATUS_REJECTED,
    STATUS_SENDING,
    STATUS_SENT,
    STATUS_SUPERSEDED,
    STATUS_VIEWED,
    STATUSES,
    TRIGGER_BEFORE_EXPIRY,
    TRIGGER_EXPIRED,
    TRIGGER_NOT_APPROVED,
    TRIGGER_NOT_VIEWED,
    TRIGGER_VIEWED_NO_REPLY,
    TRIGGERS,
    KpEvent,
    KpQuote,
    KpTimerRule,
)
from modules.kp.pim_client import PimError, PimNotSupported, is_configured, pim_client


logger = logging.getLogger(__name__)

CONFIG_KEY = "kp_settings"

DEFAULT_SEND_TEMPLATE = (
    "Здравствуйте{contact_comma}! Направляем коммерческое предложение {number} "
    "на сумму {total} {currency}. Цены действительны до {valid_until}.\n"
    "Открыть КП: {link}"
)

DEFAULT_SETTINGS: dict[str, Any] = {
    # Director's decision (28.10.2026): offers live 1–3 days.
    "validity_presets": [1, 2, 3],
    "default_valid_days": 3,
    "auto_draft": True,
    "import_pim_quotes": True,
    "send_template": DEFAULT_SEND_TEMPLATE,
    # For offers made directly in the PIM there is no dialogue to answer in;
    # client follow-ups for them go out through this WhatsApp instance.
    "followup_instance_id": "",
    "notify_telegram": True,
    "notify_chat_id": "",
    # Manager pings mirrored to WhatsApp: recipients' numbers (comma/newline
    # separated) and the instance that sends them (empty → followup_instance_id).
    "notify_whatsapp": True,
    "notify_whatsapp_numbers": "",
    "notify_whatsapp_instance_id": "",
    "tz_offset_hours": timers.DEFAULT_TZ_OFFSET_HOURS,
}

# Seeded once into an empty rules table; then they are the managers' to edit.
DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "name": "Черновик КП ждёт подтверждения",
        "trigger": TRIGGER_NOT_APPROVED,
        "offset_hours": 2,
        "action": ACTION_NOTIFY,
        "message": "КП {number} для «{customer}» на {total} {currency} ждёт подтверждения "
        "уже {hours} ч. Срок действия — до {valid_until}.",
    },
    {
        "name": "Клиент не открыл КП",
        "trigger": TRIGGER_NOT_VIEWED,
        "offset_hours": 12,
        "action": ACTION_NOTIFY,
        "message": "Клиент «{customer}» не открыл КП {number} за {hours} ч. "
        "Проверьте, дошло ли, и позвоните.",
    },
    {
        "name": "КП просмотрено, ответа нет",
        "trigger": TRIGGER_VIEWED_NO_REPLY,
        "offset_hours": 12,
        "action": ACTION_CLIENT_MESSAGE,
        "message": "Здравствуйте{contact_comma}! Удалось посмотреть коммерческое предложение "
        "{number}? Если есть вопросы по позициям, срокам или количеству — подскажем.",
    },
    {
        "name": "Срок действия заканчивается",
        "trigger": TRIGGER_BEFORE_EXPIRY,
        "offset_hours": 6,
        "action": ACTION_CLIENT_MESSAGE,
        "message": "Здравствуйте{contact_comma}! Напоминаем: цены в коммерческом предложении "
        "{number} действуют до {valid_until} включительно. Если решение принято — "
        "напишите, оформим счёт по этим ценам.",
    },
    {
        "name": "КП истекло — пересчитать",
        "trigger": TRIGGER_EXPIRED,
        "offset_hours": 0,
        "action": ACTION_NOTIFY,
        "message": "Срок КП {number} («{customer}», {total} {currency}) истёк {valid_until}, "
        "решения нет. Пересчитайте цены и наличие и перевыпустите КП — или закройте "
        "его как проигранное.",
    },
    {
        "name": "Закрыть как проигранное",
        "trigger": TRIGGER_EXPIRED,
        "offset_hours": 72,
        "action": ACTION_MARK_LOST,
        "message": "КП {number} («{customer}») закрыто как проигранное: 3 дня после "
        "окончания срока без ответа.",
    },
]

PIM_STATUS_MAP = {
    "draft": STATUS_PENDING,
    "sent": STATUS_SENT,
    "viewed": STATUS_VIEWED,
    "clarification": STATUS_CLARIFICATION,
    "accepted": STATUS_ACCEPTED,
}

# Older PIM offers are history, not work.
IMPORT_WINDOW = timedelta(days=30)
# One draft per dialogue burst: the client repeating «так что с КП?» must not
# produce a new PIM number every time.
AUTO_DRAFT_COOLDOWN = timedelta(minutes=30)
# Client follow-ups: never two in a row from the timers.
FOLLOWUP_GAP = timedelta(hours=6)
MAX_INDIVIDUAL_REFRESH = 60

EVENT_NOTIFY = "notify"
EVENT_CLIENT_MESSAGE = "client_message"
EVENT_STATUS = "status"
EVENT_INFO = "info"


class KpError(Exception):
    """Operation refused — message is user-facing."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _now() -> datetime:
    return datetime.utcnow()


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=None) - (dt.utcoffset() or timedelta()) if dt.tzinfo else dt


def _fmt_money(value: Optional[float]) -> str:
    if value is None:
        return "—"
    s = f"{value:,.2f}".replace(",", " ")
    return s[:-3] if s.endswith(".00") else s


def _phone_digits(value: Optional[str]) -> str:
    return re.sub(r"\D", "", value or "")


def _normalize_target(value: Optional[str]) -> str:
    """Phone → digits; an opaque WhatsApp address («…@lid») is kept as is."""
    raw = (value or "").strip()
    if "@" in raw:
        return raw
    return _phone_digits(raw) or raw


class KpService:
    # ─── Settings ─────────────────────────────────────────────

    async def get_settings(self) -> dict[str, Any]:
        raw = await config_service.get(CONFIG_KEY, None) or {}
        settings = {**DEFAULT_SETTINGS, **{k: v for k, v in raw.items() if k in DEFAULT_SETTINGS}}
        settings["validity_presets"] = self._clean_presets(settings["validity_presets"])
        return settings

    @staticmethod
    def _clean_presets(values: Any) -> list[int]:
        presets = sorted({int(v) for v in (values or []) if str(v).strip().isdigit()})
        return [p for p in presets if 1 <= p <= 365] or list(DEFAULT_SETTINGS["validity_presets"])

    async def save_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        current = await self.get_settings()
        for key in DEFAULT_SETTINGS:
            if key in data and data[key] is not None:
                current[key] = data[key]
        current["validity_presets"] = self._clean_presets(current["validity_presets"])
        try:
            days = int(current["default_valid_days"])
        except (TypeError, ValueError) as e:
            raise KpError("Срок действия по умолчанию — целое число дней") from e
        if not 1 <= days <= 365:
            raise KpError("Срок действия по умолчанию — от 1 до 365 дней")
        current["default_valid_days"] = days
        current["tz_offset_hours"] = float(current["tz_offset_hours"])
        for flag in ("auto_draft", "import_pim_quotes", "notify_telegram", "notify_whatsapp"):
            current[flag] = bool(current[flag])
        await config_service.set(CONFIG_KEY, current)
        return current

    # ─── PIM connection ───────────────────────────────────────

    async def status(self) -> dict[str, Any]:
        if not is_configured():
            return {"configured": False, "ok": False, "error": "Не задан ARGS_PIM_API_KEY"}
        try:
            me = await pim_client.me()
        except PimError as e:
            return {"configured": True, "ok": False, "error": str(e), "code": e.code}
        return {
            "configured": True,
            "ok": True,
            "key_name": me.get("token"),
            "can_send": bool(me.get("can_send")),
            "account_id": me.get("account_id"),
        }

    # ─── Read ─────────────────────────────────────────────────

    async def list_quotes(
        self, status: Optional[str] = None, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        async with AsyncSessionLocal() as session:
            query = select(KpQuote)
            if status:
                statuses = [s for s in status.split(",") if s]
                if STATUS_FAILED in statuses:
                    statuses.append(STATUS_SENDING)
                query = query.where(KpQuote.status.in_(statuses))
            rows = (
                await session.scalars(
                    query.order_by(KpQuote.created.desc()).limit(limit).offset(offset)
                )
            ).all()
            counts_rows = (
                await session.execute(
                    select(KpQuote.status, func.count(KpQuote.id)).group_by(KpQuote.status)
                )
            ).all()
            unread = await session.scalar(
                select(func.count(KpEvent.id)).where(
                    KpEvent.kind == EVENT_NOTIFY, KpEvent.acknowledged_at.is_(None)
                )
            )
        counts = dict.fromkeys(STATUSES, 0)
        for st, n in counts_rows:
            counts[st] = n
        counts[STATUS_FAILED] += counts.pop(STATUS_SENDING, 0)
        return {
            "quotes": [r.to_dict() for r in rows],
            "counts": counts,
            "unread_events": unread or 0,
        }

    async def get_quote(self, quote_id: int) -> dict[str, Any]:
        async with AsyncSessionLocal() as session:
            row = await session.get(KpQuote, quote_id)
            if not row:
                raise KpError("КП не найдено", 404)
            events = (
                await session.scalars(
                    select(KpEvent)
                    .where(KpEvent.quote_id == quote_id)
                    .order_by(KpEvent.created.desc())
                    .limit(100)
                )
            ).all()
            result = row.to_dict()
        result["events"] = [e.to_dict() for e in events]
        if result["outbound_message_id"]:
            from modules.outbound.service import outbound_service

            result["outbound_message"] = await outbound_service.get(result["outbound_message_id"])
        return result

    async def pdf(self, quote_id: int) -> bytes:
        async with AsyncSessionLocal() as session:
            row = await session.get(KpQuote, quote_id)
            if not row or not row.pim_id:
                raise KpError("КП не найдено", 404)
            pim_id = row.pim_id
        try:
            return await pim_client.pdf(pim_id)
        except PimError as e:
            raise KpError(f"PIM: {e}", 502) from e

    # ─── Create ───────────────────────────────────────────────

    @staticmethod
    def _pim_items(items: list[dict], with_sku: bool = True) -> list[dict]:
        out = []
        for it in items:
            entry: dict[str, Any] = {
                "name": it["name"],
                "price": it["price"],
                "count": int(it.get("count") or 1),
            }
            if it.get("delivery"):
                entry["delivery"] = it["delivery"]
            sku = (it.get("sku") or "").strip()
            if sku and with_sku:
                entry["sku"] = sku
            elif sku and sku not in entry["name"]:
                entry["name"] = f"{entry['name']} (арт. {sku})"
            out.append(entry)
        return out

    @staticmethod
    def _validate_items(items: list[dict]) -> list[dict]:
        clean = []
        for i, it in enumerate(items or [], 1):
            name = str(it.get("name") or "").strip()
            if not name:
                raise KpError(f"Позиция {i}: нет наименования")
            try:
                price = float(it.get("price"))
            except (TypeError, ValueError) as e:
                raise KpError(f"Позиция {i} «{name}»: нет цены") from e
            if price <= 0:
                raise KpError(f"Позиция {i} «{name}»: цена должна быть больше нуля")
            try:
                count = int(float(it.get("count") or 1))
            except (TypeError, ValueError) as e:
                raise KpError(f"Позиция {i} «{name}»: количество — целое число") from e
            clean.append(
                {
                    "sku": str(it.get("sku") or "").strip(),
                    "name": name,
                    "price": round(price, 2),
                    "count": max(count, 1),
                    "delivery": str(it.get("delivery") or "").strip(),
                }
            )
        if not clean:
            raise KpError("В КП нет ни одной позиции")
        if len(clean) > 200:
            raise KpError("В КП не больше 200 позиций")
        return clean

    async def _create_in_pim(
        self, customer: dict, items: list[dict], valid_until: date, request_number: str
    ) -> dict:
        payload: dict[str, Any] = {
            "customer": {
                k: v
                for k, v in {
                    "name": customer.get("name"),
                    "contact": customer.get("contact"),
                    "phone": customer.get("phone"),
                    "email": customer.get("email"),
                    "inn": customer.get("bin") or customer.get("inn"),
                    "country": "KZ",
                }.items()
                if v
            },
            "items": self._pim_items(items),
            "date_end": valid_until.isoformat(),
            "sum_with_vat": True,
        }
        if request_number:
            payload["request_number"] = request_number
        try:
            return await pim_client.create_offer(payload)
        except PimError as e:
            if e.code != "PRODUCT_NOT_FOUND":
                raise
        # The PIM catalog is not the site catalog: an article it does not know
        # is quoted as an own position, with the article kept in the name.
        payload["items"] = self._pim_items(items, with_sku=False)
        return await pim_client.create_offer(payload)

    async def create_quote(
        self,
        data: dict[str, Any],
        created_by: str,
        origin: str = ORIGIN_MANUAL,
    ) -> dict[str, Any]:
        """Create a DRAFT in the PIM and put it up for approval."""
        if not is_configured():
            raise KpError("PIM не подключён: задайте ARGS_PIM_API_KEY в .env", 503)
        settings = await self.get_settings()
        customer = {k: str(v).strip() for k, v in (data.get("customer") or {}).items() if v}
        if not customer.get("name"):
            raise KpError("Укажите покупателя (название организации)")
        items = self._validate_items(data.get("items") or [])

        delivery = data.get("delivery") or DELIVERY_LINK
        if delivery not in DELIVERY_MODES:
            raise KpError(f"Неизвестный способ отправки {delivery!r}")
        target = _normalize_target(data.get("target"))
        instance_id = (data.get("channel_instance_id") or "").strip()
        if delivery == DELIVERY_WHATSAPP and not (target and instance_id):
            raise KpError("Для отправки в WhatsApp нужны номер клиента и WhatsApp-инстанс")
        email = (data.get("email") or customer.get("email") or "").strip()

        valid_days = int(data.get("valid_days") or settings["default_valid_days"])
        if not 1 <= valid_days <= 365:
            raise KpError("Срок действия — от 1 до 365 дней")
        now = _now()
        valid_until = timers.valid_until_for(valid_days, now, settings["tz_offset_hours"])

        try:
            offer = await self._create_in_pim(
                customer, items, valid_until, (data.get("request_number") or "").strip()
            )
        except PimError as e:
            raise KpError(f"PIM не создал КП: {e}", 502) from e

        async with AsyncSessionLocal() as session:
            row = KpQuote(
                origin=origin,
                status=STATUS_PENDING,
                customer=customer,
                items=items,
                flags=list(data.get("flags") or []),
                valid_days=valid_days,
                request_number=(data.get("request_number") or "").strip() or None,
                delivery=delivery,
                channel_instance_id=instance_id or None,
                target=target or None,
                email=email or None,
                session_id=data.get("session_id"),
                reissued_from=data.get("reissued_from"),
                note=(data.get("note") or "").strip() or None,
                created_by=created_by,
                created=now,
                updated=now,
            )
            self._apply_offer_fields(row, offer)
            row.message = (data.get("message") or "").strip() or timers.render(
                settings["send_template"], self._template_values(row)
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            quote_id = row.id

        if delivery == DELIVERY_WHATSAPP:
            await self._ensure_outbound(quote_id)
        await self._event(
            quote_id,
            EVENT_INFO,
            f"Черновик {offer.get('number') or ''} создан в PIM ({created_by}), ждёт подтверждения",
        )
        result = await self.get_quote(quote_id)
        if origin == ORIGIN_ASSISTANT:
            await self._notify(
                f"🧾 Ассистент подготовил КП {result['number']} для «{customer['name']}» "
                f"на {_fmt_money(result['total'])} {result['currency'] or ''}. "
                "Нужно подтверждение на странице CRM → КП."
            )
        logger.info("KP #%s (%s) drafted by %s", quote_id, result["number"], created_by)
        return result

    async def create_from_dialogue(
        self,
        session_id: str,
        llm,
        created_by: str,
        origin: str = ORIGIN_ASSISTANT,
    ) -> dict[str, Any]:
        """Read a WhatsApp dialogue and draft the КП the client asked for."""
        from modules.chat.service import chat_service
        from modules.kp.extract import extract_request, resolve_items

        chat = await chat_service.get_session(session_id)
        if not chat:
            raise KpError("Диалог не найден", 404)
        request = await extract_request(llm, chat.get("messages") or [])
        if not request or not request["items"]:
            raise KpError("В диалоге не нашлось позиций для КП", 422)
        items, flags = await resolve_items(request["items"])
        if not items:
            raise KpError("Ни одна позиция не нашлась в каталоге с ценой: " + "; ".join(flags), 422)

        delivery, instance_id, target = DELIVERY_LINK, "", ""
        source_id = chat.get("source_id") or ""
        if chat.get("source") == "whatsapp" and ":" in source_id:
            instance_id, _, target = source_id.partition(":")
            delivery = DELIVERY_WHATSAPP
        customer = dict(request["customer"])
        phone = "" if "@" in target else _phone_digits(target)
        if phone and len(phone) >= 10:
            customer["phone"] = phone
        if not customer.get("name"):
            customer["name"] = f"Клиент WhatsApp +{phone}" if phone else "Клиент"

        return await self.create_quote(
            {
                "customer": customer,
                "items": items,
                "flags": flags,
                "delivery": delivery,
                "channel_instance_id": instance_id,
                "target": target,
                "session_id": session_id,
                "request_number": request["request_number"],
            },
            created_by=created_by,
            origin=origin,
        )

    async def maybe_auto_draft(self, session: dict, client_text: str, llm) -> None:
        """Chat hook: the client asked for a КП in a sales dialogue → draft it.

        Fire-and-forget from the chat router; never raises.
        """
        try:
            from modules.kp.extract import is_kp_request

            if not is_kp_request(client_text) or not is_configured():
                return
            settings = await self.get_settings()
            if not settings["auto_draft"]:
                return
            async with AsyncSessionLocal() as db:
                recent = await db.scalar(
                    select(func.count(KpQuote.id)).where(
                        KpQuote.session_id == session["id"],
                        KpQuote.status.in_((STATUS_PENDING, STATUS_SENDING)),
                        KpQuote.created > _now() - AUTO_DRAFT_COOLDOWN,
                    )
                )
            if recent:
                logger.info("KP auto-draft skipped: session %s has a fresh draft", session["id"])
                return
            await self.create_from_dialogue(session["id"], llm, created_by="assistant")
        except KpError as e:
            logger.info("KP auto-draft for session %s: %s", session.get("id"), e)
        except Exception:
            logger.exception("KP auto-draft failed for session %s", session.get("id"))

    # ─── Edit / approve / reject ──────────────────────────────

    async def update_quote(self, quote_id: int, data: dict[str, Any], user: str) -> dict[str, Any]:
        """Edit a draft before approval.

        Delivery and message text change here. Customer, positions or validity
        change the document itself: the PIM is asked to change it in place
        (when it supports that) or the draft is reissued under a new number.
        """
        async with AsyncSessionLocal() as session:
            row = await session.get(KpQuote, quote_id)
            if not row:
                raise KpError("КП не найдено", 404)
            if row.status not in (STATUS_PENDING, STATUS_FAILED):
                raise KpError("Править можно только КП, которое ещё не ушло клиенту", 409)
            structural = any(k in data for k in ("customer", "items", "valid_days"))

        if structural:
            return await self.reissue(
                quote_id,
                user,
                valid_days=data.get("valid_days"),
                changes={k: data[k] for k in ("customer", "items") if k in data},
                local_fields={
                    k: data[k]
                    for k in (
                        "delivery",
                        "channel_instance_id",
                        "target",
                        "email",
                        "message",
                        "note",
                    )
                    if k in data
                },
            )

        async with AsyncSessionLocal() as session:
            row = await session.get(KpQuote, quote_id)
            assert row is not None
            if "delivery" in data:
                if data["delivery"] not in DELIVERY_MODES:
                    raise KpError(f"Неизвестный способ отправки {data['delivery']!r}")
                row.delivery = data["delivery"]
            for field in ("channel_instance_id", "email", "note"):
                if field in data:
                    setattr(row, field, (data[field] or "").strip() or None)
            if "target" in data:
                row.target = _normalize_target(data["target"]) or None
            if "message" in data:
                row.message = (data["message"] or "").strip() or None
            if row.delivery == DELIVERY_WHATSAPP and not (row.target and row.channel_instance_id):
                raise KpError("Для отправки в WhatsApp нужны номер клиента и WhatsApp-инстанс")
            row.updated = _now()
            await session.commit()
            delivery, outbound_id, message = row.delivery, row.outbound_message_id, row.message

        from modules.outbound.service import outbound_service

        if delivery == DELIVERY_WHATSAPP:
            outbound_id = await self._ensure_outbound(quote_id)
            if message and outbound_id:
                await outbound_service.update_text(outbound_id, message)
        elif outbound_id:
            await outbound_service.cancel(outbound_id, "Способ отправки КП изменён")
            await self._set_fields(quote_id, outbound_message_id=None)
        return await self.get_quote(quote_id)

    async def approve(self, quote_id: int, user: str, text: Optional[str] = None) -> dict[str, Any]:
        quote = await self.get_quote(quote_id)
        if quote["status"] not in (STATUS_PENDING, STATUS_FAILED):
            raise KpError("КП уже обработано", 409)
        settings = await self.get_settings()
        if timers.is_expired(
            _parse_date(quote["valid_until"]), _now(), settings["tz_offset_hours"]
        ):
            raise KpError("Срок КП уже истёк — перевыпустите его с новым сроком", 409)

        if quote["delivery"] == DELIVERY_WHATSAPP:
            from modules.outbound.service import OutboundError, outbound_service

            outbound_id = await self._ensure_outbound(quote_id)
            try:
                await outbound_service.approve(outbound_id, user, text=text)
            except OutboundError as e:
                raise KpError(str(e), e.status_code) from e
            return await self.get_quote(quote_id)

        if not await self._claim(quote_id):
            raise KpError("КП уже обработано", 409)
        error: Optional[str] = None
        link = quote["link"]
        try:
            if quote["delivery"] == DELIVERY_EMAIL:
                to = quote["email"] or quote["customer"].get("email")
                if not to:
                    raise KpError("Не указана почта клиента")
                payload: dict[str, Any] = {"to": to, "attach_pdf": True}
                if text and text.strip():
                    payload["body"] = text.strip()
                resp = await pim_client.send_email(quote["pim_id"], payload)
                link = resp.get("link") or link
            else:
                resp = await pim_client.publish(quote["pim_id"])
                link = resp.get("link") or link
        except (PimError, KpError) as e:
            error = str(e)
        await self._finish_send(quote_id, user, error, link=link)
        return await self.get_quote(quote_id)

    async def reject(self, quote_id: int, user: str, note: str = "") -> dict[str, Any]:
        async with AsyncSessionLocal() as session:
            row = await session.get(KpQuote, quote_id)
            if not row:
                raise KpError("КП не найдено", 404)
            if row.status not in (STATUS_PENDING, STATUS_FAILED, STATUS_EXPIRED) or row.sent_at:
                raise KpError("Отклонить можно только неотправленное КП", 409)
            outbound_id = row.outbound_message_id
        if outbound_id:
            from modules.outbound.service import outbound_service

            await outbound_service.cancel(outbound_id, "КП отклонено")
        await self._close(quote_id, STATUS_REJECTED, user, note or "Отклонено до отправки")
        return await self.get_quote(quote_id)

    async def set_outcome(self, quote_id: int, status: str, user: str, note: str = "") -> dict:
        """Manager records the result: the client accepted, or the deal is lost."""
        if status not in (STATUS_ACCEPTED, STATUS_LOST):
            raise KpError("Итог КП — accepted или lost")
        quote = await self.get_quote(quote_id)
        if quote["status"] in (STATUS_SUPERSEDED, STATUS_REJECTED):
            raise KpError("КП не отправлялось клиенту или заменено новым", 409)
        if quote["pim_id"]:
            try:
                await pim_client.set_status(quote["pim_id"], status, note)
            except PimNotSupported:
                pass  # the PIM can't record it yet — kept here (docs/pim-api-for-kp.md)
            except PimError as e:
                logger.warning("PIM status for KP #%s not updated: %s", quote_id, e)
        await self._close(quote_id, status, user, note)
        return await self.get_quote(quote_id)

    async def reissue(
        self,
        quote_id: int,
        user: str,
        valid_days: Optional[int] = None,
        refresh_prices: bool = False,
        changes: Optional[dict[str, Any]] = None,
        local_fields: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """New validity (and possibly new prices) for an offer.

        If the PIM can prolong an offer in place, the number and the client link
        stay the same. Today it can't, so a new draft is created from the same
        positions and the old one is marked as replaced. Either way the result
        is a draft that needs approval again: prices and stock may have moved.
        """
        old = await self.get_quote(quote_id)
        if old["status"] in (STATUS_ACCEPTED, STATUS_SUPERSEDED):
            raise KpError("Принятое или уже заменённое КП не перевыпускается", 409)
        settings = await self.get_settings()
        days = int(valid_days or old["valid_days"] or settings["default_valid_days"])
        if not 1 <= days <= 365:
            raise KpError("Срок действия — от 1 до 365 дней")
        changes = changes or {}
        items = changes.get("items") or old["items"]
        flags = list(old["flags"])
        if refresh_prices:
            items, flags = await self._refresh_prices(items)
        customer = changes.get("customer") or old["customer"]

        if not changes and not refresh_prices and old["pim_id"] and old["status"] != STATUS_PENDING:
            valid_until = timers.valid_until_for(days, _now(), settings["tz_offset_hours"])
            try:
                offer = await pim_client.update_offer(
                    old["pim_id"], {"date_end": valid_until.isoformat()}
                )
            except PimNotSupported:
                offer = None
            except PimError as e:
                raise KpError(f"PIM: {e}", 502) from e
            if offer:
                return await self._prolonged_in_place(quote_id, offer, days, user)

        fields = {
            "delivery": old["delivery"],
            "channel_instance_id": old["channel_instance_id"],
            "target": old["target"],
            "email": old["email"],
            "note": old["note"],
            **(local_fields or {}),
        }
        if fields["delivery"] == DELIVERY_WHATSAPP and not fields["target"]:
            fields["delivery"] = DELIVERY_LINK
        new = await self.create_quote(
            {
                "customer": customer,
                "items": items,
                "flags": flags,
                "valid_days": days,
                "request_number": old["request_number"],
                "session_id": old["session_id"],
                "reissued_from": quote_id,
                "message": fields.pop("message", None),
                **fields,
            },
            created_by=user,
            origin=old["origin"] if old["origin"] != ORIGIN_PIM else ORIGIN_MANUAL,
        )
        if old["outbound_message_id"]:
            from modules.outbound.service import outbound_service

            await outbound_service.cancel(old["outbound_message_id"], "КП перевыпущено")
        if old["pim_id"] and not old["sent_at"]:
            try:
                await pim_client.delete_offer(old["pim_id"])
            except PimError:
                pass  # no DELETE in the PIM yet: the old draft stays there
        await self._set_fields(quote_id, reissued_to=new["id"])
        await self._close(quote_id, STATUS_SUPERSEDED, user, f"Перевыпущено как {new['number']}")
        return new

    async def _prolonged_in_place(self, quote_id: int, offer: dict, days: int, user: str) -> dict:
        async with AsyncSessionLocal() as session:
            row = await session.get(KpQuote, quote_id)
            assert row is not None
            self._apply_offer_fields(row, offer)
            row.valid_days = days
            mapped = PIM_STATUS_MAP.get(row.pim_status or "", STATUS_SENT)
            if row.status == STATUS_EXPIRED:
                row.status = mapped if mapped != STATUS_PENDING else STATUS_SENT
            row.updated = _now()
            await session.commit()
        await self._event(
            quote_id, EVENT_INFO, f"Срок продлён в PIM до {offer.get('valid_until')} ({user})"
        )
        return await self.get_quote(quote_id)

    async def _refresh_prices(self, items: list[dict]) -> tuple[list[dict], list[str]]:
        """Re-read prices from the catalog for positions that have an article."""
        from modules.kp.extract import resolve_items

        fresh: list[dict] = []
        flags: list[str] = []
        for it in items:
            if not it.get("sku"):
                fresh.append(it)
                flags.append(f"«{it['name']}»: своя позиция — цена не пересчитывалась")
                continue
            resolved, item_flags = await resolve_items([{"query": it["sku"], "qty": it["count"]}])
            match = next(
                (r for r in resolved if (r["sku"] or "").strip() == it["sku"].strip()), None
            )
            if match:
                fresh.append({**it, "price": match["price"], "delivery": match["delivery"]})
            else:
                fresh.append(it)
                flags.append(f"«{it['name']}»: в каталоге не нашлась — оставлена прежняя цена")
            flags.extend(f for f in item_flags if match is None and f not in flags)
        return fresh, flags

    async def delete(self, quote_id: int) -> bool:
        async with AsyncSessionLocal() as session:
            row = await session.get(KpQuote, quote_id)
            if not row:
                return False
            if row.status == STATUS_SENDING:
                raise KpError("КП сейчас отправляется", 409)
            outbound_id, pim_id, never_sent = row.outbound_message_id, row.pim_id, not row.sent_at
        if outbound_id:
            from modules.outbound.service import outbound_service

            await outbound_service.cancel(outbound_id, "КП удалено")
        if pim_id and never_sent:
            try:
                await pim_client.delete_offer(pim_id)
            except PimError:
                pass  # no DELETE in the PIM yet: the draft stays there
        async with AsyncSessionLocal() as session:
            row = await session.get(KpQuote, quote_id)
            if row:
                await session.delete(row)
            events = (
                await session.scalars(select(KpEvent).where(KpEvent.quote_id == quote_id))
            ).all()
            for e in events:
                await session.delete(e)
            await session.commit()
        return True

    # ─── Outbound queue integration ───────────────────────────

    async def _ensure_outbound(self, quote_id: int) -> int:
        """The queue message that carries this КП to WhatsApp (created once)."""
        from modules.outbound.service import outbound_service

        async with AsyncSessionLocal() as session:
            row = await session.get(KpQuote, quote_id)
            assert row is not None
            existing = row.outbound_message_id
            data = row.to_dict()
        if existing:
            msg = await outbound_service.get(existing)
            if msg and msg["status"] in ("pending", "failed"):
                return existing
        client_text = None
        if data["origin"] == ORIGIN_ASSISTANT:
            client_text = f"(КП {data['number']} — запрос из диалога)"
        message_id = await outbound_service.enqueue(
            channel="whatsapp",
            instance_id=data["channel_instance_id"],
            target=data["target"],
            text=data["message"] or "",
            session_id=data["session_id"],
            client_text=client_text,
        )
        await self._set_fields(quote_id, outbound_message_id=message_id)
        return message_id

    async def find_by_outbound(self, message_id: int) -> Optional[tuple[str, int]]:
        """("kp" | "followup", quote_id) for a queue message attached to a КП."""
        async with AsyncSessionLocal() as session:
            quote_id = await session.scalar(
                select(KpQuote.id).where(KpQuote.outbound_message_id == message_id)
            )
            if quote_id:
                return "kp", quote_id
            quote_id = await session.scalar(
                select(KpEvent.quote_id).where(
                    KpEvent.kind == EVENT_CLIENT_MESSAGE,
                    KpEvent.dedup_key == f"outbound:{message_id}",
                )
            )
            if quote_id:
                return "followup", quote_id
        return None

    async def links_for_outbound(self, message_ids: list[int]) -> dict[int, dict[str, Any]]:
        """Badge data for the approval queue: which messages carry a КП."""
        if not message_ids:
            return {}
        result: dict[int, dict[str, Any]] = {}
        async with AsyncSessionLocal() as session:
            for qid, number, mid in (
                await session.execute(
                    select(KpQuote.id, KpQuote.number, KpQuote.outbound_message_id).where(
                        KpQuote.outbound_message_id.in_(message_ids)
                    )
                )
            ).all():
                result[mid] = {"kind": "kp", "quote_id": qid, "number": number}
            keys = [f"outbound:{m}" for m in message_ids]
            for qid, key, number in (
                await session.execute(
                    select(KpEvent.quote_id, KpEvent.dedup_key, KpQuote.number)
                    .join(KpQuote, KpQuote.id == KpEvent.quote_id)
                    .where(KpEvent.dedup_key.in_(keys))
                )
            ).all():
                result[int(key.split(":", 1)[1])] = {
                    "kind": "followup",
                    "quote_id": qid,
                    "number": number,
                }
        return result

    async def before_outbound_send(self, message_id: int, text: str, link: tuple[str, int]) -> str:
        """Called by the outbound queue right before delivering a КП message.

        ``link`` is :meth:`find_by_outbound`'s answer. Returns the final text
        with the client link filled in; raises :class:`KpError` to stop sending.
        """
        kind, quote_id = link
        settings = await self.get_settings()
        async with AsyncSessionLocal() as session:
            row = await session.get(KpQuote, quote_id)
            if not row:
                raise KpError("КП, к которому относится сообщение, удалено", 409)
            expired = timers.is_expired(row.valid_until, _now(), settings["tz_offset_hours"])
            if kind == "followup":
                if row.status not in OPEN_STATUSES or expired:
                    raise KpError(
                        f"КП {row.number} уже {'истекло' if expired else 'закрыто'} — "
                        "напоминание неактуально",
                        409,
                    )
                return text.replace("{link}", row.link or "")
            if row.status not in (STATUS_PENDING, STATUS_FAILED):
                raise KpError(f"КП {row.number} уже обработано", 409)
            if expired:
                raise KpError(f"Срок КП {row.number} истёк — перевыпустите его", 409)
            pim_id = row.pim_id
            row.status = STATUS_SENDING
            row.updated = _now()
            await session.commit()

        try:
            offer = await pim_client.publish(pim_id)
        except PimError as e:
            await self._set_fields(quote_id, status=STATUS_FAILED, error=f"PIM: {e}")
            raise KpError(f"PIM не выдал ссылку на КП: {e}", 502) from e
        async with AsyncSessionLocal() as session:
            row = await session.get(KpQuote, quote_id)
            assert row is not None
            self._apply_offer_fields(row, offer)
            await session.commit()
            link_url = row.link or ""
        if not link_url:
            await self._set_fields(quote_id, status=STATUS_FAILED, error="PIM не вернул ссылку")
            raise KpError("PIM не вернул ссылку на КП", 502)
        if "{link}" in text:
            return text.replace("{link}", link_url)
        return f"{text.rstrip()}\n{link_url}"

    async def after_outbound_send(
        self, message_id: int, user: str, error: Optional[str], final_text: str
    ) -> None:
        link = await self.find_by_outbound(message_id)
        if not link:
            return
        kind, quote_id = link
        if kind == "followup":
            if not error:
                await self._event(quote_id, EVENT_INFO, f"Напоминание отправлено клиенту ({user})")
            return
        await self._finish_send(quote_id, user, error)
        if not error:
            await self._log_to_dialogue(quote_id, final_text)

    async def on_outbound_reject(self, message_id: int, user: str) -> None:
        link = await self.find_by_outbound(message_id)
        if not link:
            return
        kind, quote_id = link
        if kind == "followup":
            await self._event(quote_id, EVENT_INFO, f"Напоминание клиенту отклонено ({user})")
            return
        await self._close(quote_id, STATUS_REJECTED, user, "Отклонено в очереди подтверждения")

    async def _claim(self, quote_id: int) -> bool:
        from sqlalchemy import update

        async with AsyncSessionLocal() as session:
            claimed = await session.execute(
                update(KpQuote)
                .where(KpQuote.id == quote_id, KpQuote.status.in_((STATUS_PENDING, STATUS_FAILED)))
                .values(status=STATUS_SENDING, updated=_now())
            )
            await session.commit()
            return claimed.rowcount == 1

    async def _finish_send(
        self, quote_id: int, user: str, error: Optional[str], link: Optional[str] = None
    ) -> None:
        now = _now()
        async with AsyncSessionLocal() as session:
            row = await session.get(KpQuote, quote_id)
            if not row:
                return
            row.decided_by = user
            row.decided_at = now
            row.updated = now
            if link:
                row.link = link
            if error:
                if row.status == STATUS_SENDING:
                    row.status = STATUS_FAILED
                row.error = error
            else:
                row.status = STATUS_SENT
                row.pim_status = row.pim_status if row.pim_status not in (None, "draft") else "sent"
                row.error = None
                row.sent_at = now
            await session.commit()
            number = row.number
        if error:
            await self._event(quote_id, EVENT_INFO, f"Не удалось отправить: {error}")
        else:
            await self._event(quote_id, EVENT_STATUS, f"КП {number} отправлено клиенту ({user})")

    async def _log_to_dialogue(self, quote_id: int, text: str) -> None:
        """The КП message becomes part of the chat, so the assistant knows it was sent."""
        async with AsyncSessionLocal() as session:
            row = await session.get(KpQuote, quote_id)
            session_id = row.session_id if row else None
        if not session_id:
            return
        try:
            from modules.chat.service import chat_service

            await chat_service.add_message(session_id, "assistant", text)
        except Exception:
            logger.exception("KP #%s: failed to add the sent message to the dialogue", quote_id)

    # ─── PIM → local ──────────────────────────────────────────

    @staticmethod
    def _apply_offer_fields(row: KpQuote, offer: dict) -> None:
        if not offer:
            return
        if offer.get("id"):
            row.pim_id = int(offer["id"])
        row.number = offer.get("number") or row.number
        if offer.get("total") is not None:
            row.total = float(offer["total"])
        row.currency = offer.get("currency") or row.currency
        if offer.get("valid_until"):
            row.valid_until = _parse_date(offer["valid_until"])
        if offer.get("link"):
            row.link = offer["link"]
        if "link_active" in offer:
            row.link_active = bool(offer["link_active"])
        row.edit_url = offer.get("edit_url") or row.edit_url
        row.pim_status = offer.get("status") or row.pim_status
        if offer.get("created_at"):
            row.pim_created_at = _parse_ts(offer["created_at"])
        if offer.get("items"):
            row.items = [
                {
                    "sku": (it.get("sku") or "").strip(),
                    "name": it.get("name") or "",
                    "price": it.get("price"),
                    "count": it.get("count") or 1,
                    "delivery": it.get("delivery") or "",
                }
                for it in offer["items"]
            ]
        customer = offer.get("customer")
        if isinstance(customer, dict) and customer.get("name"):
            merged = dict(row.customer or {})
            merged.update({k: v for k, v in customer.items() if v})
            row.customer = merged

    async def apply_pim_offer(self, offer: dict, allow_import: bool = True) -> Optional[str]:
        """Bring one PIM offer into the local registry. Returns what happened."""
        if not offer.get("id"):
            return None
        now = _now()
        settings = await self.get_settings()
        cancel_outbound: Optional[int] = None
        async with AsyncSessionLocal() as session:
            row = await session.scalar(select(KpQuote).where(KpQuote.pim_id == int(offer["id"])))
            if row is None:
                created = _parse_ts(offer.get("created_at")) or now
                if not allow_import or now - created > IMPORT_WINDOW:
                    return None
                row = KpQuote(
                    origin=ORIGIN_PIM,
                    delivery=DELIVERY_LINK,
                    created_by="pim",
                    created=now,
                    updated=now,
                )
                self._apply_offer_fields(row, offer)
                row.status = PIM_STATUS_MAP.get(offer.get("status") or "", STATUS_PENDING)
                if row.status != STATUS_PENDING:
                    row.sent_at = _parse_ts(offer.get("sent_at")) or created
                if row.status in (STATUS_VIEWED, STATUS_CLARIFICATION):
                    row.viewed_at = _parse_ts(offer.get("viewed_at")) or now
                if row.status == STATUS_ACCEPTED:
                    row.closed_at = now
                phone = _phone_digits((row.customer or {}).get("phone"))
                if phone and settings["followup_instance_id"]:
                    row.target = phone
                    row.channel_instance_id = settings["followup_instance_id"]
                row.message = timers.render(settings["send_template"], self._template_values(row))
                session.add(row)
                await session.commit()
                return "imported"

            before = row.status
            prev_valid_until = row.valid_until
            self._apply_offer_fields(row, offer)
            pim_mapped = PIM_STATUS_MAP.get(offer.get("status") or "")
            if pim_mapped == STATUS_ACCEPTED and row.status != STATUS_ACCEPTED:
                row.status = STATUS_ACCEPTED
                row.closed_at = now
            elif row.status in (STATUS_PENDING, STATUS_FAILED) and pim_mapped in (
                STATUS_SENT,
                STATUS_VIEWED,
                STATUS_CLARIFICATION,
            ):
                # Sent from the PIM by hand: our queued copy must not go out twice.
                row.status = pim_mapped
                row.sent_at = row.sent_at or _parse_ts(offer.get("sent_at")) or now
                cancel_outbound = row.outbound_message_id
            elif (
                row.status == STATUS_SENT and pim_mapped in (STATUS_VIEWED, STATUS_CLARIFICATION)
            ) or (row.status == STATUS_VIEWED and pim_mapped == STATUS_CLARIFICATION):
                row.status = pim_mapped
            elif (
                row.status == STATUS_EXPIRED
                and row.valid_until != prev_valid_until
                and not timers.is_expired(row.valid_until, now, settings["tz_offset_hours"])
            ):
                # Prolonged in the PIM by hand.
                row.status = (
                    pim_mapped
                    if pim_mapped and pim_mapped != STATUS_PENDING
                    else (STATUS_SENT if row.sent_at else STATUS_PENDING)
                )
            if row.status in (STATUS_VIEWED, STATUS_CLARIFICATION) and not row.viewed_at:
                row.viewed_at = _parse_ts(offer.get("viewed_at")) or now
            row.updated = now
            await session.commit()
            after, quote_id, number = row.status, row.id, row.number

        if cancel_outbound:
            from modules.outbound.service import outbound_service

            await outbound_service.cancel(cancel_outbound, "КП отправлено из PIM вручную")
        if after != before:
            await self._event(
                quote_id,
                EVENT_STATUS,
                f"КП {number}: {self._status_label(before)} → "
                f"{self._status_label(after)} (по данным PIM)",
            )
            if after == STATUS_ACCEPTED:
                await self._notify(f"✅ Клиент принял КП {number}")
            return "updated"
        return "unchanged"

    async def sync_from_pim(self) -> dict[str, Any]:
        if not is_configured():
            return {"ok": False, "error": "PIM не подключён"}
        settings = await self.get_settings()
        stats = {"imported": 0, "updated": 0, "unchanged": 0, "refreshed": 0, "errors": 0}
        try:
            offers = await pim_client.list_offers(limit=50)
        except PimError as e:
            return {"ok": False, "error": str(e), **stats}
        seen = set()
        for offer in offers:
            seen.add(offer.get("id"))
            result = await self.apply_pim_offer(offer, allow_import=settings["import_pim_quotes"])
            if result in stats:
                stats[result] += 1

        # The list shows only the latest 50 — older open offers are read one by one.
        async with AsyncSessionLocal() as session:
            stale = (
                await session.scalars(
                    select(KpQuote.pim_id)
                    .where(
                        KpQuote.pim_id.is_not(None),
                        KpQuote.status.in_((STATUS_PENDING, *OPEN_STATUSES)),
                    )
                    .limit(MAX_INDIVIDUAL_REFRESH + len(seen))
                )
            ).all()
        for pim_id in [p for p in stale if p not in seen][:MAX_INDIVIDUAL_REFRESH]:
            try:
                await self.apply_pim_offer(await pim_client.get_offer(pim_id), allow_import=False)
                stats["refreshed"] += 1
            except PimError as e:
                stats["errors"] += 1
                logger.warning("KP sync: PIM offer %s: %s", pim_id, e)
        return {"ok": True, **stats}

    # ─── Timers ───────────────────────────────────────────────

    async def run_timers(self, now: Optional[datetime] = None) -> dict[str, int]:
        now = now or _now()
        settings = await self.get_settings()
        tz = settings["tz_offset_hours"]
        stats = {"expired": 0, "fired": 0}

        async with AsyncSessionLocal() as session:
            rows = (
                await session.scalars(select(KpQuote).where(KpQuote.status.in_(timers.EXPIRABLE)))
            ).all()
            newly_expired = []
            for row in rows:
                if timers.is_expired(row.valid_until, now, tz):
                    row.status = STATUS_EXPIRED
                    row.updated = now
                    newly_expired.append((row.id, row.number, row.outbound_message_id, row.sent_at))
            await session.commit()
        for quote_id, number, outbound_id, sent_at in newly_expired:
            stats["expired"] += 1
            await self._event(quote_id, EVENT_STATUS, f"Срок КП {number} истёк")
            if outbound_id and not sent_at:
                from modules.outbound.service import outbound_service

                await outbound_service.cancel(outbound_id, "Срок КП истёк до подтверждения")

        rules = [r for r in await self.list_rules() if r["enabled"]]
        if not rules:
            return stats
        async with AsyncSessionLocal() as session:
            quotes = (
                await session.scalars(
                    select(KpQuote).where(KpQuote.status.in_((*timers.EXPIRABLE, STATUS_EXPIRED)))
                )
            ).all()
            fired_keys = {
                (qid, key)
                for qid, key in (
                    await session.execute(
                        select(KpEvent.quote_id, KpEvent.dedup_key).where(
                            KpEvent.quote_id.in_([q.id for q in quotes] or [0]),
                            KpEvent.dedup_key.like("rule:%"),
                        )
                    )
                ).all()
            }
            snapshot = [q.to_dict() | {"_valid_until": q.valid_until} for q in quotes]
            times = {
                q.id: timers.QuoteTimes(q.status, q.created, q.sent_at, q.viewed_at, q.valid_until)
                for q in quotes
            }

        for quote in snapshot:
            for rule in rules:
                key = timers.dedup_key(rule["id"], quote["_valid_until"])
                if (quote["id"], key) in fired_keys:
                    continue
                if not timers.rule_due(rule, times[quote["id"]], now, tz):
                    continue
                if await self._fire(rule, quote, key, now):
                    stats["fired"] += 1
                    fired_keys.add((quote["id"], key))
        return stats

    async def _fire(self, rule: dict, quote: dict, key: str, now: datetime) -> bool:
        """Run one due rule. False = try again next round (nothing recorded)."""
        ref_field = {
            TRIGGER_NOT_VIEWED: "sent_at",
            TRIGGER_VIEWED_NO_REPLY: "viewed_at",
        }.get(rule["trigger"], "created")
        text = timers.render(
            rule.get("message") or rule["name"], self._template_values(quote, now, ref_field)
        )
        action = rule["action"]

        if action == ACTION_MARK_LOST:
            if not quote["sent_at"]:
                # A draft nobody sent isn't a lost deal, just an expired draft.
                await self._event(
                    quote["id"],
                    EVENT_INFO,
                    rule["name"] + ": КП не отправлялось — пропущено",
                    rule["id"],
                    key,
                )
                return True
            await self.set_outcome(quote["id"], STATUS_LOST, "timer", rule["name"])
            await self._event(quote["id"], EVENT_NOTIFY, text, rule["id"], key)
            await self._notify(f"⏱ {text}")
            return True

        if action == ACTION_CLIENT_MESSAGE:
            if not (quote["target"] and quote["channel_instance_id"]):
                # Offers made in the PIM: the customer's phone, if a WhatsApp
                # number for reminders has been chosen since.
                phone = _phone_digits((quote["customer"] or {}).get("phone"))
                instance = (await self.get_settings())["followup_instance_id"]
                if phone and instance:
                    quote = {**quote, "target": phone, "channel_instance_id": instance}
                    await self._set_fields(quote["id"], target=phone, channel_instance_id=instance)
            if not (quote["target"] and quote["channel_instance_id"]):
                await self._event(
                    quote["id"],
                    EVENT_NOTIFY,
                    f"{rule['name']}: напишите клиенту сами (нет WhatsApp-канала для этого КП):\n{text}",
                    rule["id"],
                    key,
                )
                return True
            if await self._has_pending_client_message(quote, now):
                return False
            from modules.outbound.service import outbound_service

            message_id = await outbound_service.enqueue(
                channel="whatsapp",
                instance_id=quote["channel_instance_id"],
                target=quote["target"],
                text=text,
                session_id=quote["session_id"],
                client_text=f"(таймер КП {quote['number']}: {rule['name']})",
            )
            await self._event(
                quote["id"], EVENT_CLIENT_MESSAGE, text, rule["id"], f"outbound:{message_id}"
            )
            # Separate dedup record: the outbound key above links the queue
            # message to the quote, this one stops the rule from firing again.
            await self._event(
                quote["id"],
                EVENT_INFO,
                f"{rule['name']}: сообщение клиенту ждёт подтверждения",
                rule["id"],
                key,
            )
            return True

        await self._event(quote["id"], EVENT_NOTIFY, text, rule["id"], key)
        await self._notify(f"⏱ {text}")
        return True

    async def _has_pending_client_message(self, quote: dict, now: datetime) -> bool:
        from modules.outbound.models import OutboundMessage

        async with AsyncSessionLocal() as session:
            recent = (
                await session.execute(
                    select(KpEvent.dedup_key, KpEvent.created).where(
                        KpEvent.quote_id == quote["id"], KpEvent.kind == EVENT_CLIENT_MESSAGE
                    )
                )
            ).all()
            if any(created > now - FOLLOWUP_GAP for _, created in recent):
                return True
            ids = [int(k.split(":", 1)[1]) for k, _ in recent if k and k.startswith("outbound:")]
            if quote["outbound_message_id"]:
                ids.append(quote["outbound_message_id"])
            if not ids:
                return False
            pending = await session.scalar(
                select(func.count(OutboundMessage.id)).where(
                    OutboundMessage.id.in_(ids), OutboundMessage.status == "pending"
                )
            )
        return bool(pending)

    # ─── Rules CRUD ───────────────────────────────────────────

    async def list_rules(self) -> list[dict[str, Any]]:
        async with AsyncSessionLocal() as session:
            rows = (
                await session.scalars(
                    select(KpTimerRule).order_by(KpTimerRule.sort, KpTimerRule.id)
                )
            ).all()
            return [r.to_dict() for r in rows]

    @staticmethod
    def _validate_rule(data: dict[str, Any], partial: bool = False) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        if not partial or "name" in data:
            name = str(data.get("name") or "").strip()
            if not name:
                raise KpError("У таймера должно быть название")
            clean["name"] = name[:200]
        if not partial or "trigger" in data:
            if data.get("trigger") not in TRIGGERS:
                raise KpError(f"Неизвестное событие {data.get('trigger')!r}")
            clean["trigger"] = data["trigger"]
        if not partial or "action" in data:
            if data.get("action") not in ACTIONS:
                raise KpError(f"Неизвестное действие {data.get('action')!r}")
            clean["action"] = data["action"]
        if not partial or "offset_hours" in data:
            try:
                hours = float(data.get("offset_hours") or 0)
            except (TypeError, ValueError) as e:
                raise KpError("Время — число часов") from e
            if not 0 <= hours <= 24 * 90:
                raise KpError("Время — от 0 до 2160 часов")
            clean["offset_hours"] = hours
        if "message" in data:
            clean["message"] = (data.get("message") or "").strip() or None
        if "enabled" in data:
            clean["enabled"] = bool(data["enabled"])
        if "sort" in data:
            clean["sort"] = int(data.get("sort") or 0)
        if clean.get("action") == ACTION_CLIENT_MESSAGE and not clean.get(
            "message", data.get("message")
        ):
            raise KpError("Для сообщения клиенту нужен текст")
        return clean

    @retry_on_busy()
    async def create_rule(self, data: dict[str, Any]) -> dict[str, Any]:
        clean = self._validate_rule(data)
        async with AsyncSessionLocal() as session:
            row = KpTimerRule(**clean)
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.to_dict()

    @retry_on_busy()
    async def update_rule(self, rule_id: int, data: dict[str, Any]) -> dict[str, Any]:
        clean = self._validate_rule(data, partial=True)
        async with AsyncSessionLocal() as session:
            row = await session.get(KpTimerRule, rule_id)
            if not row:
                raise KpError("Таймер не найден", 404)
            for k, v in clean.items():
                setattr(row, k, v)
            if row.action == ACTION_CLIENT_MESSAGE and not row.message:
                raise KpError("Для сообщения клиенту нужен текст")
            row.updated = _now()
            await session.commit()
            await session.refresh(row)
            return row.to_dict()

    @retry_on_busy()
    async def delete_rule(self, rule_id: int) -> bool:
        async with AsyncSessionLocal() as session:
            row = await session.get(KpTimerRule, rule_id)
            if not row:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def ensure_default_rules(self) -> int:
        """Seed the default timers into an empty table (first start only)."""
        async with AsyncSessionLocal() as session:
            if await session.scalar(select(func.count(KpTimerRule.id))):
                return 0
            for i, rule in enumerate(DEFAULT_RULES):
                session.add(KpTimerRule(**rule, sort=i * 10, enabled=True))
            await session.commit()
        return len(DEFAULT_RULES)

    # ─── Events ───────────────────────────────────────────────

    async def list_events(self, unread_only: bool = False, limit: int = 50) -> list[dict[str, Any]]:
        async with AsyncSessionLocal() as session:
            query = select(KpEvent, KpQuote.number, KpQuote.customer).join(
                KpQuote, KpQuote.id == KpEvent.quote_id
            )
            query = query.where(KpEvent.kind == EVENT_NOTIFY)
            if unread_only:
                query = query.where(KpEvent.acknowledged_at.is_(None))
            rows = (
                await session.execute(query.order_by(KpEvent.created.desc()).limit(limit))
            ).all()
        return [
            e.to_dict() | {"number": number, "customer": (customer or {}).get("name")}
            for e, number, customer in rows
        ]

    @retry_on_busy()
    async def ack_event(self, event_id: int, user: str) -> dict[str, Any]:
        async with AsyncSessionLocal() as session:
            row = await session.get(KpEvent, event_id)
            if not row:
                raise KpError("Событие не найдено", 404)
            row.acknowledged_by = user
            row.acknowledged_at = _now()
            await session.commit()
            await session.refresh(row)
            return row.to_dict()

    @retry_on_busy()
    async def _event(
        self,
        quote_id: int,
        kind: str,
        text: str,
        rule_id: Optional[int] = None,
        dedup_key: Optional[str] = None,
    ) -> None:
        async with AsyncSessionLocal() as session:
            session.add(
                KpEvent(
                    quote_id=quote_id,
                    kind=kind,
                    text=text,
                    rule_id=rule_id,
                    dedup_key=dedup_key,
                    created=_now(),
                )
            )
            await session.commit()

    # ─── Helpers ──────────────────────────────────────────────

    @retry_on_busy()
    async def _set_fields(self, quote_id: int, **fields: Any) -> None:
        async with AsyncSessionLocal() as session:
            row = await session.get(KpQuote, quote_id)
            if not row:
                return
            for k, v in fields.items():
                setattr(row, k, v)
            row.updated = _now()
            await session.commit()

    async def _close(self, quote_id: int, status: str, user: str, note: str = "") -> None:
        now = _now()
        async with AsyncSessionLocal() as session:
            row = await session.get(KpQuote, quote_id)
            if not row:
                return
            before = row.status
            row.status = status
            row.closed_at = now
            row.decided_by = row.decided_by or user
            row.updated = now
            if note:
                row.note = f"{row.note}\n{note}".strip() if row.note else note
            await session.commit()
            number = row.number
        await self._event(
            quote_id,
            EVENT_STATUS,
            f"КП {number}: {self._status_label(before)} → {self._status_label(status)} ({user})"
            + (f": {note}" if note else ""),
        )

    @staticmethod
    def _status_label(status: str) -> str:
        return {
            STATUS_PENDING: "на подтверждении",
            STATUS_SENDING: "отправляется",
            STATUS_SENT: "отправлено",
            STATUS_VIEWED: "просмотрено",
            STATUS_CLARIFICATION: "уточнение",
            STATUS_ACCEPTED: "принято",
            STATUS_EXPIRED: "истекло",
            STATUS_LOST: "проиграно",
            STATUS_REJECTED: "отклонено",
            STATUS_SUPERSEDED: "перевыпущено",
            STATUS_FAILED: "не отправлено",
        }.get(status, status)

    @staticmethod
    def _template_values(
        quote: Any, now: Optional[datetime] = None, ref_field: str = "created"
    ) -> dict[str, Any]:
        q = quote if isinstance(quote, dict) else quote.to_dict()
        customer = q.get("customer") or {}
        contact = (customer.get("contact") or "").strip()
        valid_until = _parse_date(q.get("valid_until"))
        ref = _parse_ts(q.get(ref_field)) if q.get(ref_field) else None
        hours = int((now - ref).total_seconds() // 3600) if now and ref else ""
        return {
            "number": q.get("number") or "",
            "customer": customer.get("name") or "",
            "contact": contact,
            "contact_comma": f", {contact}" if contact else "",
            "total": _fmt_money(q.get("total")),
            "currency": q.get("currency") or "₸",
            "valid_until": valid_until.strftime("%d.%m.%Y") if valid_until else "",
            "link": q.get("link") or "",
            "hours": hours,
        }

    async def _notify(self, text: str) -> None:
        """Ping to the manager/director (Telegram + WhatsApp). Best-effort, never raises."""
        settings = await self.get_settings()
        await self._notify_telegram(settings, text)
        await self._notify_whatsapp(settings, text)

    @staticmethod
    async def _notify_telegram(settings: dict[str, Any], text: str) -> None:
        if not settings["notify_telegram"]:
            return
        token = os.getenv("KP_TELEGRAM_BOT_TOKEN") or os.getenv("LEAD_TELEGRAM_BOT_TOKEN", "")
        chat_id = (
            str(settings["notify_chat_id"] or "").strip()
            or os.getenv("KP_TELEGRAM_CHAT_ID", "")
            or os.getenv("LEAD_TELEGRAM_CHAT_ID", "")
        )
        if not token.strip() or not chat_id.strip():
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"https://api.telegram.org/bot{token.strip()}/sendMessage",
                    json={
                        "chat_id": chat_id.strip(),
                        "text": text,
                        "disable_web_page_preview": True,
                    },
                )
        except Exception as e:
            logger.warning("KP Telegram notification failed: %s", e)

    @staticmethod
    async def _notify_whatsapp(settings: dict[str, Any], text: str) -> None:
        """Internal ping to staff numbers — not a client message, so no approval queue."""
        if not settings["notify_whatsapp"]:
            return
        instance_id = str(
            settings["notify_whatsapp_instance_id"] or settings["followup_instance_id"] or ""
        ).strip()
        numbers = [
            _normalize_target(n)
            for n in re.split(r"[,;\n]+", str(settings["notify_whatsapp_numbers"] or ""))
            if n.strip()
        ]
        if not instance_id or not numbers:
            return
        from modules.outbound.sender import send_whatsapp

        for number in numbers:
            try:
                await send_whatsapp(instance_id, number, text)
            except Exception as e:
                logger.warning("KP WhatsApp notification to %s failed: %s", number, e)

    async def handle_webhook(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Push from the PIM (docs/pim-api-for-kp.md): an offer changed."""
        offer = payload.get("offer") if isinstance(payload.get("offer"), dict) else payload
        result = await self.apply_pim_offer(offer, allow_import=True)
        if payload.get("event") == "offer.viewed" and result == "unchanged":
            await self._set_fields_if_viewed(offer)
        return {"ok": True, "result": result}

    async def _set_fields_if_viewed(self, offer: dict) -> None:
        async with AsyncSessionLocal() as session:
            row = await session.scalar(select(KpQuote).where(KpQuote.pim_id == int(offer["id"])))
            if row and row.status == STATUS_SENT:
                row.status = STATUS_VIEWED
                row.viewed_at = _parse_ts(offer.get("viewed_at")) or _now()
                await session.commit()


kp_service = KpService()
