"""Outbound approval queue and channel monitoring.

The single place that decides whether an assistant reply goes to the client
right away or waits for a human (MASTER WORKFLOW §1.2: the approval logic lives
in one place and is not spread across scenarios). Channels only ask
:meth:`OutboundService.submit` and do what it says.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import and_, func, select, update

from db.database import AsyncSessionLocal
from db.retry import retry_on_busy
from modules.chat.models import ChatMessage, ChatSession
from modules.core.service import config_service
from modules.outbound.models import (
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_REJECTED,
    STATUS_SENT,
    STATUSES,
    OutboundMessage,
)
from modules.outbound.sender import DeliveryError, deliver


logger = logging.getLogger(__name__)

CONFIG_KEY = "outbound_approval"

MODE_AUTO = "auto"
MODE_APPROVAL = "approval"
MODES = (MODE_AUTO, MODE_APPROVAL)

# Transitional status: claimed by one approve call, so a double click (or two
# operators at once) can't send the same reply twice.
STATUS_SENDING = "sending"

# §2.5: the only text that reaches the client without approval — no prices,
# goods, terms or promises.
DEFAULT_ACK_TEXT = "Здравствуйте! Ваше сообщение получено, менеджер ответит вам в ближайшее время."
# One acknowledgement per burst of messages, not one per message.
ACK_COOLDOWN = timedelta(minutes=30)

DEFAULT_UNANSWERED_MINUTES = 10
DEFAULT_PENDING_ALERT_MINUTES = 30
# Older silence is history, not an incident.
MONITOR_LOOKBACK = timedelta(hours=72)

REJECTED_PLACEHOLDER = "(черновик ответа отклонён — клиенту не отправлялся)"

# chat_sessions.source values per monitored channel
CHANNEL_SOURCES: dict[str, tuple[str, ...]] = {
    "whatsapp": ("whatsapp",),
    "telegram": ("telegram", "telegram_bot"),
    "widget": ("widget",),
}


class OutboundError(Exception):
    """Operation refused — message is user-facing."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _instance_key(channel: str, instance_id: str) -> str:
    return f"{channel}:{instance_id}"


class OutboundService:
    # ─── Settings ─────────────────────────────────────────────

    async def get_settings(self) -> dict[str, Any]:
        raw = await config_service.get(CONFIG_KEY, None) or {}
        return {
            "instances": dict(raw.get("instances") or {}),
            "unanswered_minutes": int(raw.get("unanswered_minutes") or DEFAULT_UNANSWERED_MINUTES),
            "pending_alert_minutes": int(
                raw.get("pending_alert_minutes") or DEFAULT_PENDING_ALERT_MINUTES
            ),
        }

    async def save_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        current = await self.get_settings()
        if "instances" in data:
            instances: dict[str, Any] = {}
            for key, cfg in (data["instances"] or {}).items():
                mode = (cfg or {}).get("mode", MODE_AUTO)
                if mode not in MODES:
                    raise OutboundError(f"Неизвестный режим {mode!r}")
                instances[key] = {
                    "mode": mode,
                    "ack_text": ((cfg or {}).get("ack_text") or "").strip(),
                }
            current["instances"] = instances
        for field in ("unanswered_minutes", "pending_alert_minutes"):
            if data.get(field) is not None:
                value = int(data[field])
                if value < 1:
                    raise OutboundError(f"{field} должно быть ≥ 1")
                current[field] = value
        await config_service.set(CONFIG_KEY, current)
        return current

    async def instance_config(self, channel: str, instance_id: str) -> dict[str, str]:
        settings = await self.get_settings()
        cfg = settings["instances"].get(_instance_key(channel, instance_id)) or {}
        return {"mode": cfg.get("mode", MODE_AUTO), "ack_text": cfg.get("ack_text", "")}

    async def is_approval(self, channel: str, instance_id: str) -> bool:
        return (await self.instance_config(channel, instance_id))["mode"] == MODE_APPROVAL

    # ─── Submit (called by channels) ──────────────────────────

    @retry_on_busy()
    async def submit(
        self,
        channel: str,
        instance_id: str,
        target: str,
        text: str,
        session_id: Optional[str] = None,
        client_text: Optional[str] = None,
    ) -> dict[str, Any]:
        """Decide what happens to a freshly generated reply.

        Returns ``{"action": "send"}`` (channel sends it itself) or
        ``{"action": "queued", "id", "ack_text"}`` — the channel then sends only
        ``ack_text`` when it is non-empty.
        """
        cfg = await self.instance_config(channel, instance_id)
        if cfg["mode"] != MODE_APPROVAL:
            return {"action": "send", "mode": cfg["mode"]}

        now = datetime.utcnow()
        async with AsyncSessionLocal() as session:
            recent_ack = await session.scalar(
                select(func.count(OutboundMessage.id)).where(
                    OutboundMessage.channel == channel,
                    OutboundMessage.target == target,
                    OutboundMessage.ack_sent.is_(True),
                    OutboundMessage.created > now - ACK_COOLDOWN,
                )
            )
            ack_text = ""
            if not recent_ack:
                ack_text = cfg["ack_text"] or DEFAULT_ACK_TEXT

            chat_message_id = None
            if session_id:
                chat_message_id = await session.scalar(
                    select(ChatMessage.id)
                    .where(
                        ChatMessage.session_id == session_id,
                        ChatMessage.role == "assistant",
                        ChatMessage.is_active.is_(True),
                    )
                    .order_by(ChatMessage.created.desc())
                    .limit(1)
                )

            row = OutboundMessage(
                channel=channel,
                instance_id=instance_id,
                target=target,
                session_id=session_id,
                chat_message_id=chat_message_id,
                client_text=client_text,
                draft_text=text,
                text=text,
                status=STATUS_PENDING,
                ack_sent=bool(ack_text),
                created=now,
                updated=now,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            logger.info(
                "Outbound #%s queued for approval (%s %s → %s)",
                row.id,
                channel,
                instance_id,
                target,
            )
            return {"action": "queued", "id": row.id, "ack_text": ack_text, "mode": MODE_APPROVAL}

    @retry_on_busy()
    async def enqueue(
        self,
        channel: str,
        instance_id: str,
        target: str,
        text: str,
        session_id: Optional[str] = None,
        client_text: Optional[str] = None,
    ) -> int:
        """Put a message straight into the queue, whatever the channel's mode.

        For messages the assistant does not send as a reply — a КП, a timer
        reminder — which always need a human, even on an «auto» channel.
        """
        now = datetime.utcnow()
        async with AsyncSessionLocal() as session:
            row = OutboundMessage(
                channel=channel,
                instance_id=instance_id,
                target=target,
                session_id=session_id,
                client_text=client_text,
                draft_text=text,
                text=text,
                status=STATUS_PENDING,
                ack_sent=False,
                created=now,
                updated=now,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.id

    @retry_on_busy()
    async def cancel(self, message_id: int, reason: str) -> None:
        """Withdraw a pending message without a human decision (the КП changed)."""
        async with AsyncSessionLocal() as session:
            row = await session.get(OutboundMessage, message_id)
            if not row or row.status not in (STATUS_PENDING, STATUS_FAILED):
                return
            row.status = STATUS_REJECTED
            row.error = reason
            row.decided_by = "system"
            row.decided_at = datetime.utcnow()
            row.updated = datetime.utcnow()
            await session.commit()

    # ─── CRUD ─────────────────────────────────────────────────

    async def list_messages(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        async with AsyncSessionLocal() as session:
            query = select(OutboundMessage)
            if status:
                statuses = [s for s in status.split(",") if s]
                if STATUS_FAILED in statuses:
                    statuses.append(STATUS_SENDING)
                query = query.where(OutboundMessage.status.in_(statuses))
            # Pending work oldest-first (it is a queue); history newest-first.
            order = (
                OutboundMessage.created.asc()
                if status == STATUS_PENDING
                else OutboundMessage.created.desc()
            )
            rows = (await session.scalars(query.order_by(order).limit(limit).offset(offset))).all()

            counts_rows = (
                await session.execute(
                    select(OutboundMessage.status, func.count(OutboundMessage.id)).group_by(
                        OutboundMessage.status
                    )
                )
            ).all()
        counts = dict.fromkeys(STATUSES, 0)
        for st, n in counts_rows:
            key = STATUS_FAILED if st == STATUS_SENDING else st
            counts[key] = counts.get(key, 0) + n
        messages = [r.to_dict() for r in rows]
        kp_links = await _kp_links([m["id"] for m in messages])
        for m in messages:
            m["kp"] = kp_links.get(m["id"])
        return {"messages": messages, "counts": counts}

    async def get(self, message_id: int) -> Optional[dict[str, Any]]:
        async with AsyncSessionLocal() as session:
            row = await session.get(OutboundMessage, message_id)
            if not row:
                return None
            message = row.to_dict()
        message["kp"] = (await _kp_links([message_id])).get(message_id)
        return message

    @retry_on_busy()
    async def update_text(self, message_id: int, text: str) -> dict[str, Any]:
        text = (text or "").strip()
        if not text:
            raise OutboundError("Текст ответа пуст")
        async with AsyncSessionLocal() as session:
            row = await session.get(OutboundMessage, message_id)
            if not row:
                raise OutboundError("Сообщение не найдено", 404)
            if row.status not in (STATUS_PENDING, STATUS_FAILED):
                raise OutboundError("Отправленное или отклонённое сообщение не правится", 409)
            row.text = text
            row.updated = datetime.utcnow()
            await session.commit()
            await session.refresh(row)
            return row.to_dict()

    async def approve(
        self, message_id: int, decided_by: str, text: Optional[str] = None
    ) -> dict[str, Any]:
        """Send the reply to the client. Edits in ``text`` are saved first."""
        if text is not None:
            await self.update_text(message_id, text)

        now = datetime.utcnow()
        async with AsyncSessionLocal() as session:
            claimed = await session.execute(
                update(OutboundMessage)
                .where(
                    OutboundMessage.id == message_id,
                    OutboundMessage.status.in_((STATUS_PENDING, STATUS_FAILED)),
                )
                .values(status=STATUS_SENDING, updated=now)
            )
            await session.commit()
            if claimed.rowcount != 1:
                exists = await session.get(OutboundMessage, message_id)
                if not exists:
                    raise OutboundError("Сообщение не найдено", 404)
                raise OutboundError("Сообщение уже обработано", 409)
            row = await session.get(OutboundMessage, message_id)
            assert row is not None
            channel, instance_id, target, final_text = (
                row.channel,
                row.instance_id,
                row.target,
                row.text,
            )

        error: Optional[str] = None
        is_kp = False
        kp_link = None
        try:
            from modules.kp.service import kp_service

            kp_link = await kp_service.find_by_outbound(message_id)
        except Exception:
            # The КП lookup must never block an ordinary reply — but a КП text
            # with an unfilled link placeholder must never reach the client.
            logger.exception("Outbound #%s: КП lookup failed", message_id)
            if "{link}" in final_text:
                error = "Не удалось проверить КП — повторите отправку"
        if kp_link:
            is_kp = True
            try:
                # The client link comes from the PIM at the moment of sending.
                final_text = await kp_service.before_outbound_send(message_id, final_text, kp_link)
            except Exception as e:
                error = str(e) or type(e).__name__
        if not error:
            try:
                await deliver(channel, instance_id, target, final_text)
            except DeliveryError as e:
                error = str(e)
                logger.warning("Outbound #%s delivery failed: %s", message_id, error)

        async with AsyncSessionLocal() as session:
            row = await session.get(OutboundMessage, message_id)
            assert row is not None
            row.decided_by = decided_by
            row.decided_at = now
            row.updated = datetime.utcnow()
            if error:
                row.status = STATUS_FAILED
                row.error = error
            else:
                row.status = STATUS_SENT
                row.error = None
                row.sent_at = datetime.utcnow()
                if is_kp:
                    # Record what the client really got: the text with the link.
                    row.text = final_text
            await session.commit()
            await session.refresh(row)
            result = row.to_dict()
            snapshot = {
                "session_id": row.session_id,
                "chat_message_id": row.chat_message_id,
                "draft_text": row.draft_text,
                "client_text": row.client_text or "",
            }

        if is_kp:
            try:
                from modules.kp.service import kp_service

                await kp_service.after_outbound_send(message_id, decided_by, error, final_text)
            except Exception:
                logger.exception("Outbound #%s: КП status update failed", message_id)
        if not error:
            if final_text != snapshot["draft_text"]:
                await self._rewrite_history(snapshot["chat_message_id"], final_text)
            await self._file_to_crm(
                snapshot["session_id"], channel, target, snapshot["client_text"], final_text
            )
        return result

    @retry_on_busy()
    async def reject(self, message_id: int, decided_by: str) -> dict[str, Any]:
        async with AsyncSessionLocal() as session:
            row = await session.get(OutboundMessage, message_id)
            if not row:
                raise OutboundError("Сообщение не найдено", 404)
            if row.status not in (STATUS_PENDING, STATUS_FAILED):
                raise OutboundError("Сообщение уже обработано", 409)
            row.status = STATUS_REJECTED
            row.decided_by = decided_by
            row.decided_at = datetime.utcnow()
            row.updated = datetime.utcnow()
            await session.commit()
            await session.refresh(row)
            chat_message_id = row.chat_message_id
            result = row.to_dict()
        # The assistant must not "remember" saying something the client never saw.
        await self._rewrite_history(chat_message_id, REJECTED_PLACEHOLDER)
        try:
            from modules.kp.service import kp_service

            await kp_service.on_outbound_reject(message_id, decided_by)
        except Exception:
            logger.exception("Outbound #%s: КП status update on reject failed", message_id)
        return result

    @retry_on_busy()
    async def delete(self, message_id: int) -> bool:
        async with AsyncSessionLocal() as session:
            row = await session.get(OutboundMessage, message_id)
            if not row:
                return False
            if row.status == STATUS_SENDING:
                raise OutboundError("Сообщение сейчас отправляется", 409)
            await session.delete(row)
            await session.commit()
            return True

    async def _rewrite_history(self, chat_message_id: Optional[str], content: str) -> None:
        if not chat_message_id:
            return
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(ChatMessage)
                    .where(ChatMessage.id == chat_message_id)
                    .values(content=content, edited=True)
                )
                await session.commit()
        except Exception:
            logger.exception("Failed to sync chat history for message %s", chat_message_id)

    async def _file_to_crm(
        self,
        session_id: Optional[str],
        channel: str,
        target: str,
        client_text: str,
        final_text: str,
    ) -> None:
        """amoCRM note with what the client actually received.

        In approval mode the chat router skips its own note (it only has the
        draft), so the turn is filed here once the reply really went out.
        """
        if channel != "whatsapp" or not session_id:
            return
        try:
            async with AsyncSessionLocal() as session:
                lead_id = await session.scalar(
                    select(ChatSession.amocrm_lead_id).where(ChatSession.id == session_id)
                )
            if not lead_id:
                return
            from app.dependencies import get_container
            from modules.channels.whatsapp.events import WhatsAppMessageSent

            asyncio.create_task(
                get_container().event_bus.publish(
                    WhatsAppMessageSent(
                        session_id=session_id,
                        lead_id=int(lead_id),
                        sender=target,
                        user_message=client_text,
                        assistant_response=final_text,
                    )
                )
            )
        except Exception:
            logger.exception("Failed to file approved reply to amoCRM")

    # ─── Monitoring ───────────────────────────────────────────

    async def monitor(self) -> dict[str, Any]:
        settings = await self.get_settings()
        now = datetime.utcnow()
        unanswered_after = timedelta(minutes=settings["unanswered_minutes"])
        pending_alert_after = timedelta(minutes=settings["pending_alert_minutes"])

        queue = await self._queue_stats(now)
        activity = await self._conversation_activity(now)
        whatsapp = await self._whatsapp_channels(settings, activity, now, unanswered_after)
        crm = await self._crm_status()

        other_channels = []
        for channel in ("telegram", "widget"):
            convs = [c for c in activity if c["channel"] == channel]
            other_channels.append(
                self._channel_summary(channel, channel, convs, now, unanswered_after)
            )

        alerts: list[dict[str, str]] = []
        for ch in whatsapp:
            if not ch["enabled"]:
                continue
            if not ch["bot_running"]:
                alerts.append({"level": "error", "text": f"WhatsApp {ch['name']}: бот не запущен"})
            if ch["provider"] == "bridge" and ch["bridge_status"] != "connected":
                detail = ch.get("bridge_error") or ch["bridge_status"]
                alerts.append(
                    {
                        "level": "error",
                        "text": f"WhatsApp {ch['name']}: телефон не на связи ({detail})",
                    }
                )
        for ch in [*whatsapp, *other_channels]:
            if ch["unanswered_count"]:
                alerts.append(
                    {
                        "level": "error",
                        "text": f"{ch['name']}: без ответа {ch['unanswered_count']} "
                        f"диалог(ов) дольше {settings['unanswered_minutes']} мин",
                    }
                )
        if queue["oldest_pending_seconds"] and queue["oldest_pending_seconds"] > (
            pending_alert_after.total_seconds()
        ):
            alerts.append(
                {
                    "level": "warning",
                    "text": f"Ответы ждут подтверждения дольше {settings['pending_alert_minutes']} мин",
                }
            )
        if queue["failed"]:
            alerts.append({"level": "error", "text": f"Не доставлено ответов: {queue['failed']}"})
        if not crm["connected"]:
            alerts.append({"level": "warning", "text": "amoCRM не подключён — лиды не заводятся"})

        levels = {a["level"] for a in alerts}
        overall = "error" if "error" in levels else "warning" if levels else "ok"
        return {
            "status": overall,
            "checked_at": now.isoformat() + "Z",
            "alerts": alerts,
            "queue": queue,
            "whatsapp": whatsapp,
            "channels": other_channels,
            "crm": crm,
            "settings": {
                "unanswered_minutes": settings["unanswered_minutes"],
                "pending_alert_minutes": settings["pending_alert_minutes"],
            },
        }

    async def _queue_stats(self, now: datetime) -> dict[str, Any]:
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        async with AsyncSessionLocal() as session:
            pending = await session.scalar(
                select(func.count(OutboundMessage.id)).where(
                    OutboundMessage.status == STATUS_PENDING
                )
            )
            oldest = await session.scalar(
                select(func.min(OutboundMessage.created)).where(
                    OutboundMessage.status == STATUS_PENDING
                )
            )
            failed = await session.scalar(
                select(func.count(OutboundMessage.id)).where(
                    OutboundMessage.status.in_((STATUS_FAILED, STATUS_SENDING))
                )
            )
            sent_today = await session.scalar(
                select(func.count(OutboundMessage.id)).where(
                    OutboundMessage.status == STATUS_SENT,
                    OutboundMessage.sent_at >= day_start,
                )
            )
        return {
            "pending": pending or 0,
            "oldest_pending_seconds": int((now - oldest).total_seconds()) if oldest else None,
            "failed": failed or 0,
            "sent_today": sent_today or 0,
        }

    async def _conversation_activity(self, now: datetime) -> list[dict[str, Any]]:
        """Per conversation: last inbound, last outbound, and who spoke last."""
        sources = [s for group in CHANNEL_SOURCES.values() for s in group]
        since = now - MONITOR_LOOKBACK
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(
                        ChatSession.id,
                        ChatSession.source,
                        ChatSession.source_id,
                        ChatMessage.role,
                        func.max(ChatMessage.created),
                    )
                    .join(ChatMessage, ChatMessage.session_id == ChatSession.id)
                    .where(
                        ChatSession.source.in_(sources),
                        ChatMessage.is_active.is_(True),
                        ChatMessage.role.in_(("user", "assistant")),
                        ChatMessage.created >= since,
                    )
                    .group_by(
                        ChatSession.id, ChatSession.source, ChatSession.source_id, ChatMessage.role
                    )
                )
            ).all()

            by_session: dict[str, dict[str, Any]] = {}
            for session_id, source, source_id, role, last in rows:
                channel = next(
                    (ch for ch, group in CHANNEL_SOURCES.items() if source in group), source
                )
                entry = by_session.setdefault(
                    session_id,
                    {
                        "session_id": session_id,
                        "channel": channel,
                        "source_id": source_id or "",
                        "last_in": None,
                        "last_out": None,
                    },
                )
                entry["last_in" if role == "user" else "last_out"] = last

            waiting = [
                e["session_id"]
                for e in by_session.values()
                if e["last_in"] and (not e["last_out"] or e["last_out"] < e["last_in"])
            ]
            previews: dict[str, str] = {}
            if waiting:
                last_user = (
                    select(ChatMessage.session_id, func.max(ChatMessage.created).label("mx"))
                    .where(
                        ChatMessage.session_id.in_(waiting),
                        ChatMessage.role == "user",
                        ChatMessage.is_active.is_(True),
                    )
                    .group_by(ChatMessage.session_id)
                    .subquery()
                )
                for sid, content in (
                    await session.execute(
                        select(ChatMessage.session_id, ChatMessage.content).join(
                            last_user,
                            and_(
                                ChatMessage.session_id == last_user.c.session_id,
                                ChatMessage.created == last_user.c.mx,
                            ),
                        )
                    )
                ).all():
                    previews[sid] = (content or "")[:200]
            for sid in waiting:
                by_session[sid]["preview"] = previews.get(sid, "")
        return list(by_session.values())

    def _channel_summary(
        self,
        key: str,
        name: str,
        convs: list[dict[str, Any]],
        now: datetime,
        unanswered_after: timedelta,
        approval: bool = False,
    ) -> dict[str, Any]:
        last_in = max((c["last_in"] for c in convs if c["last_in"]), default=None)
        last_out = max((c["last_out"] for c in convs if c["last_out"]), default=None)
        unanswered = []
        for c in convs:
            if not c["last_in"]:
                continue
            if c["last_out"] and c["last_out"] >= c["last_in"]:
                continue
            waited = now - c["last_in"]
            if waited < unanswered_after:
                continue
            target = c["source_id"].split(":", 1)[1] if ":" in c["source_id"] else c["source_id"]
            unanswered.append(
                {
                    "session_id": c["session_id"],
                    "target": target,
                    "waiting_seconds": int(waited.total_seconds()),
                    "preview": c.get("preview", ""),
                }
            )
        unanswered.sort(key=lambda u: -u["waiting_seconds"])
        return {
            "key": key,
            "name": name,
            "approval": approval,
            "conversations_72h": len(convs),
            "last_inbound_at": last_in.isoformat() + "Z" if last_in else None,
            "last_outbound_at": last_out.isoformat() + "Z" if last_out else None,
            "unanswered_count": len(unanswered),
            "unanswered": unanswered[:20],
        }

    async def _whatsapp_channels(
        self,
        settings: dict[str, Any],
        activity: list[dict[str, Any]],
        now: datetime,
        unanswered_after: timedelta,
    ) -> list[dict[str, Any]]:
        from modules.channels.whatsapp.bridge import get_bridge_client, is_bridge_instance
        from modules.channels.whatsapp.service import whatsapp_instance_service
        from whatsapp_manager import whatsapp_manager

        instances = await whatsapp_instance_service.list_instances()
        result = []
        for inst in instances:
            instance_id = inst["id"]
            cfg = settings["instances"].get(_instance_key("whatsapp", instance_id)) or {}
            mode = cfg.get("mode", MODE_AUTO)
            convs = [
                c
                for c in activity
                if c["channel"] == "whatsapp" and c["source_id"].startswith(f"{instance_id}:")
            ]
            summary = self._channel_summary(
                f"whatsapp:{instance_id}",
                inst.get("name") or instance_id,
                convs,
                now,
                unanswered_after,
                approval=mode == MODE_APPROVAL,
            )
            bot = await whatsapp_manager.get_bot_status(instance_id)
            bridge_status, bridge_error, connected_at = None, None, None
            if is_bridge_instance(inst):
                full = await whatsapp_instance_service.get_instance_with_token(instance_id)
                client = get_bridge_client(full or inst)
                try:
                    status = await asyncio.wait_for(client.get_status(), timeout=5)
                    bridge_status = status.get("status") or "unknown"
                    bridge_error = status.get("last_error")
                    connected_at = status.get("connected_at")
                except Exception as e:
                    bridge_status = "unreachable"
                    bridge_error = str(e) or type(e).__name__
                finally:
                    await client.close()
            summary.update(
                {
                    "instance_id": instance_id,
                    "enabled": bool(inst.get("enabled")),
                    "provider": inst.get("provider") or "cloud",
                    "mode": mode,
                    "ack_text": cfg.get("ack_text", ""),
                    "bot_running": bool(bot.get("running")),
                    "bot_uptime_seconds": bot.get("uptime_seconds"),
                    "bridge_status": bridge_status,
                    "bridge_error": bridge_error,
                    "bridge_connected_at": connected_at,
                }
            )
            result.append(summary)
        return result

    async def _crm_status(self) -> dict[str, Any]:
        try:
            from modules.crm.service import amocrm_service

            config = await amocrm_service.get_config() or {}
        except Exception:
            logger.debug("amoCRM config read failed", exc_info=True)
            config = {}
        return {
            "connected": bool(config.get("is_connected")),
            "subdomain": config.get("subdomain"),
            "auto_create_lead": bool(config.get("auto_create_lead")),
            "last_sync_at": config.get("last_sync_at"),
        }


async def _kp_links(message_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Which queue messages carry a КП (badge + link in the admin panel)."""
    try:
        from modules.kp.service import kp_service

        return await kp_service.links_for_outbound(message_ids)
    except Exception:
        logger.debug("КП links lookup failed", exc_info=True)
        return {}


outbound_service = OutboundService()
