"""Очередь подтверждения исходящих ответов.

Ключевые свойства:

1. в режиме ``approval`` ответ ассистента клиенту не уходит — канал получает
   только автоответ о приёме, и то один раз на серию сообщений;
2. одобрение отправляет ТЕКУЩИЙ текст (с правкой), а история диалога
   переписывается под то, что клиент реально увидел;
3. двойное одобрение не отправляет ответ дважды;
4. отклонённый черновик не остаётся в памяти ассистента как сказанное.
"""

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

import db.models  # noqa: F401  — registers every table so FKs resolve
from db.database import Base
from modules.chat.models import ChatMessage, ChatSession
from modules.core.models import Workspace
from modules.outbound import service as outbound_module
from modules.outbound.models import STATUS_FAILED, STATUS_REJECTED, STATUS_SENT
from modules.outbound.sender import DeliveryError
from modules.outbound.service import (
    DEFAULT_ACK_TEXT,
    REJECTED_PLACEHOLDER,
    OutboundError,
    OutboundService,
)


INSTANCE = "wa-77085442089"
PHONE = "77001234567"
SESSION = "chat_wa_1"


class _Config:
    def __init__(self):
        self.store: dict = {}

    async def get(self, key, default=None):
        return self.store.get(key, default)

    async def set(self, key, value):
        self.store[key] = value
        return True


@pytest_asyncio.fixture()
async def env(test_engine, test_session_factory, monkeypatch):
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_factory() as session:
        session.add(Workspace(id=1, name="test", slug="test"))
        await session.flush()
        session.add(
            ChatSession(
                id=SESSION,
                title="WhatsApp Bot",
                source="whatsapp",
                source_id=f"{INSTANCE}:{PHONE}",
                workspace_id=1,
            )
        )
        session.add(ChatMessage(id="m1", session_id=SESSION, role="user", content="Есть АВР 630А?"))
        session.add(
            ChatMessage(
                id="m2",
                session_id=SESSION,
                role="assistant",
                content="Черновик ответа",
                created=datetime.utcnow() + timedelta(seconds=1),
            )
        )
        await session.commit()

    sent: list[tuple] = []
    fail = {"on": False}

    async def fake_deliver(channel, instance_id, target, text):
        if fail["on"]:
            raise DeliveryError("bridge down")
        sent.append((channel, instance_id, target, text))

    config = _Config()
    monkeypatch.setattr(outbound_module, "AsyncSessionLocal", test_session_factory)
    monkeypatch.setattr(outbound_module, "deliver", fake_deliver)
    monkeypatch.setattr(outbound_module, "config_service", config)

    svc = OutboundService()

    async def no_crm(*args, **kwargs):
        return None

    monkeypatch.setattr(svc, "_file_to_crm", no_crm)
    return {"svc": svc, "sent": sent, "fail": fail, "factory": test_session_factory}


async def _approval_on(svc, ack_text=""):
    await svc.save_settings(
        {"instances": {f"whatsapp:{INSTANCE}": {"mode": "approval", "ack_text": ack_text}}}
    )


async def _submit(svc, text="Черновик ответа"):
    return await svc.submit("whatsapp", INSTANCE, PHONE, text, SESSION, "Есть АВР 630А?")


async def _chat_text(factory, message_id):
    async with factory() as session:
        return await session.scalar(select(ChatMessage.content).where(ChatMessage.id == message_id))


async def test_auto_mode_sends_directly_and_queues_nothing(env):
    svc = env["svc"]
    decision = await _submit(svc)
    assert decision["action"] == "send"
    assert (await svc.list_messages())["messages"] == []


async def test_approval_queues_and_acks_once_per_burst(env):
    svc = env["svc"]
    await _approval_on(svc)

    first = await _submit(svc)
    second = await _submit(svc, "Ещё один ответ")

    assert first["action"] == "queued"
    assert first["ack_text"] == DEFAULT_ACK_TEXT
    assert second["action"] == "queued"
    assert second["ack_text"] == ""  # клиент уже получил автоответ
    assert env["sent"] == []  # сам ответ клиенту не ушёл

    listed = await svc.list_messages(status="pending")
    assert listed["counts"]["pending"] == 2
    assert listed["messages"][0]["id"] == first["id"]  # очередь — старые первыми


async def test_custom_ack_text(env):
    svc = env["svc"]
    await _approval_on(svc, ack_text="Приняли, ответим скоро")
    assert (await _submit(svc))["ack_text"] == "Приняли, ответим скоро"


async def test_approve_sends_edited_text_and_rewrites_history(env):
    svc = env["svc"]
    await _approval_on(svc)
    queued = await _submit(svc)

    result = await svc.approve(queued["id"], "director", text="Да, АВР 630А есть — 36 шт.")

    assert result["status"] == STATUS_SENT
    assert result["edited"] is True
    assert result["draft_text"] == "Черновик ответа"
    assert env["sent"] == [("whatsapp", INSTANCE, PHONE, "Да, АВР 630А есть — 36 шт.")]
    assert await _chat_text(env["factory"], "m2") == "Да, АВР 630А есть — 36 шт."


async def test_double_approve_sends_once(env):
    svc = env["svc"]
    await _approval_on(svc)
    queued = await _submit(svc)

    await svc.approve(queued["id"], "director")
    with pytest.raises(OutboundError) as err:
        await svc.approve(queued["id"], "director")

    assert err.value.status_code == 409
    assert len(env["sent"]) == 1


async def test_failed_delivery_is_kept_and_can_be_retried(env):
    svc = env["svc"]
    await _approval_on(svc)
    queued = await _submit(svc)

    env["fail"]["on"] = True
    failed = await svc.approve(queued["id"], "director")
    assert failed["status"] == STATUS_FAILED
    assert failed["error"] == "bridge down"

    env["fail"]["on"] = False
    retried = await svc.approve(queued["id"], "director")
    assert retried["status"] == STATUS_SENT
    assert retried["error"] is None


async def test_reject_removes_draft_from_assistant_memory(env):
    svc = env["svc"]
    await _approval_on(svc)
    queued = await _submit(svc)

    result = await svc.reject(queued["id"], "director")

    assert result["status"] == STATUS_REJECTED
    assert env["sent"] == []
    assert await _chat_text(env["factory"], "m2") == REJECTED_PLACEHOLDER
    with pytest.raises(OutboundError):
        await svc.approve(queued["id"], "director")


async def test_sent_message_is_not_editable(env):
    svc = env["svc"]
    await _approval_on(svc)
    queued = await _submit(svc)
    await svc.approve(queued["id"], "director")

    with pytest.raises(OutboundError) as err:
        await svc.update_text(queued["id"], "поздно")
    assert err.value.status_code == 409


async def test_unknown_mode_rejected(env):
    with pytest.raises(OutboundError):
        await env["svc"].save_settings({"instances": {"whatsapp:x": {"mode": "yolo"}}})


def test_unanswered_detection():
    svc = OutboundService()
    now = datetime.utcnow()
    convs = [
        # клиент написал 20 мин назад, ответа нет → без ответа
        {
            "session_id": "a",
            "source_id": f"{INSTANCE}:{PHONE}",
            "last_in": now - timedelta(minutes=20),
            "last_out": now - timedelta(hours=1),
            "preview": "Есть АВР?",
        },
        # ответ уже был после вопроса
        {
            "session_id": "b",
            "source_id": f"{INSTANCE}:7002",
            "last_in": now - timedelta(minutes=20),
            "last_out": now - timedelta(minutes=19),
        },
        # написал только что — ещё не инцидент
        {
            "session_id": "c",
            "source_id": f"{INSTANCE}:7003",
            "last_in": now - timedelta(minutes=2),
            "last_out": None,
        },
    ]
    summary = svc._channel_summary("whatsapp:x", "WA", convs, now, timedelta(minutes=10))

    assert summary["unanswered_count"] == 1
    assert summary["unanswered"][0]["target"] == PHONE
    assert summary["unanswered"][0]["preview"] == "Есть АВР?"


async def test_conversation_activity_finds_unanswered_dialogue(env, test_session_factory):
    svc = env["svc"]
    async with test_session_factory() as session:
        session.add(
            ChatMessage(
                id="m3",
                session_id=SESSION,
                role="user",
                content="Ау, вы тут?",
                created=datetime.utcnow() + timedelta(seconds=2),
            )
        )
        await session.commit()

    activity = await svc._conversation_activity(datetime.utcnow() + timedelta(minutes=30))

    assert len(activity) == 1
    conv = activity[0]
    assert conv["channel"] == "whatsapp"
    assert conv["last_out"] < conv["last_in"]
    assert conv["preview"] == "Ау, вы тут?"
