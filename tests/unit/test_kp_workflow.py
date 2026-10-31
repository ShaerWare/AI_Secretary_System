"""КП: черновик в PIM → подтверждение человеком → отправка → таймеры.

Ключевые свойства:

1. ассистент создаёт только ЧЕРНОВИК; клиенту ничего не уходит до подтверждения;
2. WhatsApp-КП лежит в общей очереди подтверждения, и одобрение из очереди и
   из вкладки «КП» — одно и то же действие; ссылка из PIM подставляется в
   момент отправки;
3. просроченное КП не отправляется, а очередь чистится сама;
4. отправленное из PIM вручную не уходит клиенту второй раз;
5. таймеры срабатывают один раз, сообщения клиенту — только через очередь.
"""

import sys
import types
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

import db.models  # noqa: F401  — registers every table so FKs resolve
from db.database import Base
from modules.chat.models import ChatMessage, ChatSession
from modules.core.models import Workspace
from modules.kp import service as kp_module
from modules.kp.models import (
    ACTION_CLIENT_MESSAGE,
    ACTION_MARK_LOST,
    STATUS_EXPIRED,
    STATUS_LOST,
    STATUS_PENDING,
    STATUS_REJECTED,
    STATUS_SENT,
    STATUS_SUPERSEDED,
    STATUS_VIEWED,
    TRIGGER_EXPIRED,
    TRIGGER_VIEWED_NO_REPLY,
    KpEvent,
)
from modules.kp.pim_client import PimError, PimNotSupported
from modules.kp.service import KpError, kp_service
from modules.outbound import service as outbound_module
from modules.outbound.models import OutboundMessage
from modules.outbound.service import outbound_service


INSTANCE = "wa-77085442089"
PHONE = "77001234567"
SESSION = "chat_wa_kp"
LINK = "https://stalkerelectric.kz/cp/abc"


class _Config:
    def __init__(self):
        self.store: dict = {}

    async def get(self, key, default=None):
        return self.store.get(key, default)

    async def set(self, key, value):
        self.store[key] = value
        return True


class FakePim:
    def __init__(self):
        self.offers: dict[int, dict] = {}
        self.created: list[dict] = []
        self.published: list[int] = []
        self.next_id = 1300
        self.unknown_skus: set[str] = set()

    async def create_offer(self, payload):
        for it in payload["items"]:
            if it.get("sku") in self.unknown_skus:
                raise PimError("Товар не найден", "PRODUCT_NOT_FOUND", 400, "items[0].sku")
        self.created.append(payload)
        self.next_id += 1
        offer = {
            "id": self.next_id,
            "number": f"КП-{self.next_id - 1280:04d}",
            "status": "draft",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "valid_until": payload["date_end"],
            "expired": False,
            "currency": "₸",
            "total": sum(i["price"] * i["count"] for i in payload["items"]),
            "customer": payload["customer"],
            "items": payload["items"],
            "link": None,
            "link_active": False,
            "edit_url": f"http://ar-gs.ru/commercial-offers/edit/{self.next_id}",
        }
        self.offers[self.next_id] = offer
        return dict(offer)

    async def publish(self, offer_id):
        self.published.append(offer_id)
        offer = self.offers[offer_id]
        offer.update(status="sent", link=LINK, link_active=True)
        return dict(offer)

    async def list_offers(self, limit=50, q=None):
        return [dict(o) for o in self.offers.values()][:limit]

    async def get_offer(self, offer_id):
        return dict(self.offers[offer_id])

    async def update_offer(self, offer_id, payload):
        raise PimNotSupported("Нет метода", "ROUTE_NOT_FOUND", 404)

    async def set_status(self, offer_id, status, reason=""):
        raise PimNotSupported("Нет метода", "ROUTE_NOT_FOUND", 404)

    async def delete_offer(self, offer_id):
        raise PimNotSupported("Нет метода", "ROUTE_NOT_FOUND", 404)


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
                title="WhatsApp",
                source="whatsapp",
                source_id=f"{INSTANCE}:{PHONE}",
                workspace_id=1,
            )
        )
        await session.commit()

    sent: list[tuple] = []

    async def fake_deliver(channel, instance_id, target, text):
        sent.append((channel, instance_id, target, text))

    pim = FakePim()
    config = _Config()
    for module in (kp_module, outbound_module):
        monkeypatch.setattr(module, "AsyncSessionLocal", test_session_factory)

    # modules.chat.service pulls PIL/OCR in; the КП only needs add_message.
    class _Chat:
        async def add_message(self, session_id, role, content):
            async with test_session_factory() as s:
                s.add(
                    ChatMessage(
                        id=uuid.uuid4().hex, session_id=session_id, role=role, content=content
                    )
                )
                await s.commit()

    monkeypatch.setitem(
        sys.modules, "modules.chat.service", types.SimpleNamespace(chat_service=_Chat())
    )
    monkeypatch.setattr(outbound_module, "deliver", fake_deliver)
    monkeypatch.setattr(outbound_module, "config_service", config)
    monkeypatch.setattr(kp_module, "config_service", config)
    monkeypatch.setattr(kp_module, "pim_client", pim)
    monkeypatch.setattr(kp_module, "is_configured", lambda: True)

    async def no_notify(text):
        return None

    monkeypatch.setattr(kp_service, "_notify", no_notify)
    await kp_service.ensure_default_rules()
    return {"pim": pim, "sent": sent, "factory": test_session_factory, "monkeypatch": monkeypatch}


ITEMS = [
    {
        "sku": "02008001",
        "name": "Кабель КГ-хл 1х70",
        "price": 9483,
        "count": 30,
        "delivery": "5-7 дней",
    },
    {"sku": "050600097", "name": "КГтп 1х25", "price": 2958, "count": 10, "delivery": "В наличии"},
]


async def _draft(**overrides):
    data = {
        "customer": {"name": "ТОО Тест", "contact": "Азамат", "phone": PHONE},
        "items": ITEMS,
        "delivery": "whatsapp",
        "channel_instance_id": INSTANCE,
        "target": PHONE,
        "session_id": SESSION,
        **overrides,
    }
    return await kp_service.create_quote(data, created_by="assistant", origin="assistant")


async def _outbound(factory, message_id):
    async with factory() as s:
        return await s.get(OutboundMessage, message_id)


def _shift_now(monkeypatch, delta: timedelta):
    real = datetime.utcnow
    monkeypatch.setattr(kp_module, "_now", lambda: real() + delta)


async def test_draft_goes_to_pim_and_queue_but_not_to_client(env):
    quote = await _draft()

    assert quote["status"] == STATUS_PENDING
    assert quote["number"] and quote["pim_id"]
    payload = env["pim"].created[0]
    assert payload["customer"]["name"] == "ТОО Тест"
    assert payload["sum_with_vat"] is True
    # по умолчанию 3 дня (директор, 28.10.2026)
    assert quote["valid_days"] == 3
    assert env["pim"].published == []
    assert env["sent"] == []

    msg = await _outbound(env["factory"], quote["outbound_message_id"])
    assert msg.status == "pending"
    assert "{link}" in msg.text and quote["number"] in msg.text


async def test_approve_from_kp_tab_publishes_and_sends_link(env):
    quote = await _draft()
    result = await kp_service.approve(quote["id"], "director")

    assert result["status"] == STATUS_SENT
    assert result["link"] == LINK
    assert env["pim"].published == [quote["pim_id"]]
    assert len(env["sent"]) == 1
    _, instance, target, text = env["sent"][0]
    assert (instance, target) == (INSTANCE, PHONE)
    assert LINK in text and "{link}" not in text

    msg = await _outbound(env["factory"], quote["outbound_message_id"])
    assert msg.status == "sent" and LINK in msg.text
    # отправленное КП стало частью диалога — ассистент знает, что оно ушло
    async with env["factory"]() as s:
        contents = (
            await s.scalars(select(ChatMessage.content).where(ChatMessage.session_id == SESSION))
        ).all()
    assert any(LINK in c for c in contents)


async def test_approve_from_queue_is_the_same_action(env):
    quote = await _draft()
    await outbound_service.approve(quote["outbound_message_id"], "manager")

    after = await kp_service.get_quote(quote["id"])
    assert after["status"] == STATUS_SENT
    assert after["decided_by"] == "manager"
    with pytest.raises(KpError):
        await kp_service.approve(quote["id"], "director")
    assert len(env["sent"]) == 1


async def test_queue_shows_kp_badge(env):
    quote = await _draft()
    listing = await outbound_service.list_messages(status="pending")
    badge = listing["messages"][0]["kp"]
    assert badge == {"kind": "kp", "quote_id": quote["id"], "number": quote["number"]}


async def test_reject_in_queue_rejects_quote(env):
    quote = await _draft()
    await outbound_service.reject(quote["outbound_message_id"], "director")
    assert (await kp_service.get_quote(quote["id"]))["status"] == STATUS_REJECTED
    assert env["sent"] == []


async def test_unknown_article_is_quoted_as_own_position(env):
    env["pim"].unknown_skus = {"02008001"}
    await _draft()
    names = [i["name"] for i in env["pim"].created[0]["items"]]
    assert "Кабель КГ-хл 1х70 (арт. 02008001)" in names
    assert all("sku" not in i for i in env["pim"].created[0]["items"])


async def test_expired_draft_cannot_be_sent_and_leaves_queue(env):
    quote = await _draft(valid_days=1)
    _shift_now(env["monkeypatch"], timedelta(days=3))

    with pytest.raises(KpError, match="истёк"):
        await kp_service.approve(quote["id"], "director")

    stats = await kp_service.run_timers(kp_module._now())
    assert stats["expired"] == 1
    assert (await kp_service.get_quote(quote["id"]))["status"] == STATUS_EXPIRED
    msg = await _outbound(env["factory"], quote["outbound_message_id"])
    assert msg.status == "rejected"
    assert env["sent"] == []


async def test_sent_from_pim_by_hand_is_not_sent_twice(env):
    quote = await _draft()
    env["pim"].offers[quote["pim_id"]]["status"] = "sent"

    await kp_service.sync_from_pim()

    after = await kp_service.get_quote(quote["id"])
    assert after["status"] == STATUS_SENT
    msg = await _outbound(env["factory"], quote["outbound_message_id"])
    assert msg.status == "rejected"


async def test_viewed_followup_is_queued_once_and_gets_the_link(env):
    quote = await _draft()
    await kp_service.approve(quote["id"], "director")
    env["pim"].offers[quote["pim_id"]]["status"] = "viewed"
    await kp_service.sync_from_pim()
    assert (await kp_service.get_quote(quote["id"]))["status"] == STATUS_VIEWED

    rule = next(r for r in await kp_service.list_rules() if r["trigger"] == TRIGGER_VIEWED_NO_REPLY)
    assert rule["action"] == ACTION_CLIENT_MESSAGE
    await kp_service.update_rule(rule["id"], {"message": "Посмотрели {number}? {link}"})

    later = datetime.utcnow() + timedelta(hours=13)
    await kp_service.run_timers(later)
    await kp_service.run_timers(later + timedelta(minutes=10))

    async with env["factory"]() as s:
        pending = (
            await s.scalars(select(OutboundMessage).where(OutboundMessage.status == "pending"))
        ).all()
    assert len(pending) == 1
    # the offer is already published, so the reminder carries the real link
    assert pending[0].text == f"Посмотрели {quote['number']}? {LINK}"
    assert len(env["sent"]) == 1  # only the КП itself so far — the reminder waits

    await outbound_service.approve(pending[0].id, "manager")
    assert env["sent"][-1][3] == f"Посмотрели {quote['number']}? {LINK}"


async def test_expired_offer_is_closed_as_lost_after_three_days(env):
    quote = await _draft(valid_days=1)
    await kp_service.approve(quote["id"], "director")
    rule = next(r for r in await kp_service.list_rules() if r["action"] == ACTION_MARK_LOST)
    assert rule["trigger"] == TRIGGER_EXPIRED

    _shift_now(env["monkeypatch"], timedelta(days=3))
    await kp_service.run_timers(kp_module._now())
    assert (await kp_service.get_quote(quote["id"]))["status"] == STATUS_EXPIRED

    await kp_service.run_timers(kp_module._now() + timedelta(days=3))
    assert (await kp_service.get_quote(quote["id"]))["status"] == STATUS_LOST
    async with env["factory"]() as s:
        notes = (await s.scalars(select(KpEvent.text).where(KpEvent.kind == "notify"))).all()
    assert any("истёк" in n for n in notes)


async def test_reissue_without_pim_support_creates_new_draft(env):
    quote = await _draft(valid_days=1)
    await kp_service.approve(quote["id"], "director")

    new = await kp_service.reissue(quote["id"], "manager", valid_days=2)

    assert new["id"] != quote["id"] and new["number"] != quote["number"]
    assert new["status"] == STATUS_PENDING and new["reissued_from"] == quote["id"]
    assert new["valid_days"] == 2
    old = await kp_service.get_quote(quote["id"])
    assert old["status"] == STATUS_SUPERSEDED and old["reissued_to"] == new["id"]
    # новый черновик снова ждёт подтверждения в очереди
    msg = await _outbound(env["factory"], new["outbound_message_id"])
    assert msg.status == "pending" and new["number"] in msg.text


async def test_pim_offers_are_imported_without_retroactive_actions(env):
    pim = env["pim"]
    pim.offers[999] = {
        "id": 999,
        "number": "КП-0005",
        "status": "viewed",
        "created_at": (datetime.utcnow() - timedelta(days=16)).isoformat() + "Z",
        "valid_until": (datetime.utcnow() - timedelta(days=16)).date().isoformat(),
        "expired": True,
        "currency": "₸",
        "total": 100,
        "customer": {"name": "ТОО Старый", "phone": "+7 775 000 00 00"},
        "items": [],
        "link": LINK,
        "link_active": False,
    }
    stats = await kp_service.sync_from_pim()
    assert stats["imported"] == 1

    await kp_service.run_timers(datetime.utcnow() + timedelta(days=10))
    quotes = (await kp_service.list_quotes())["quotes"]
    imported = next(q for q in quotes if q["number"] == "КП-0005")
    # видно как «истекло», но задним числом в проигранные не записано
    assert imported["status"] == STATUS_EXPIRED
    assert imported["origin"] == "pim"


async def test_auto_draft_only_on_kp_request(env, monkeypatch):
    calls = []

    async def fake_create(session_id, llm, created_by, origin="assistant"):
        calls.append(session_id)
        return {}

    monkeypatch.setattr(kp_service, "create_from_dialogue", fake_create)
    session = {"id": SESSION, "source": "whatsapp"}
    await kp_service.maybe_auto_draft(session, "АВР 630А есть в наличии?", llm=None)
    assert calls == []
    await kp_service.maybe_auto_draft(session, "Пришлите КП на эти позиции", llm=None)
    assert calls == [SESSION]


async def test_notify_mirrors_to_whatsapp_staff_numbers(monkeypatch):
    import modules.outbound.sender as sender_module

    sent: list[tuple[str, str, str]] = []

    async def fake_send(instance_id, target, text):
        sent.append((instance_id, target, text))
        if target == "77010000002":
            raise sender_module.DeliveryError("bridge down")

    monkeypatch.setattr(sender_module, "send_whatsapp", fake_send)
    settings = {
        **kp_module.DEFAULT_SETTINGS,
        "notify_telegram": False,
        "followup_instance_id": "wa-followup",
        "notify_whatsapp_numbers": "+7 701 000-00-01, 77010000002\n77010000003",
    }
    await kp_service._notify_whatsapp(settings, "🧾 КП готово")
    # Empty instance falls back to the follow-up one; a failed number doesn't stop the rest.
    assert sent == [
        ("wa-followup", "77010000001", "🧾 КП готово"),
        ("wa-followup", "77010000002", "🧾 КП готово"),
        ("wa-followup", "77010000003", "🧾 КП готово"),
    ]

    sent.clear()
    await kp_service._notify_whatsapp({**settings, "notify_whatsapp": False}, "x")
    await kp_service._notify_whatsapp({**settings, "notify_whatsapp_numbers": ""}, "x")
    assert sent == []
