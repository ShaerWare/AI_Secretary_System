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
from modules.kp import messenger
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

    notified: list[tuple] = []

    async def record_notify(text, quote=None):
        notified.append((text, quote))

    monkeypatch.setattr(kp_service, "_notify", record_notify)
    await kp_service.ensure_default_rules()
    return {
        "pim": pim,
        "sent": sent,
        "notified": notified,
        "factory": test_session_factory,
        "monkeypatch": monkeypatch,
    }


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


# ─── КП in the managers' messengers (modules/kp/messenger.py) ──────────

STAFF = "77712288488"


def _staff_settings(env):
    env["monkeypatch"].setattr(
        kp_module.config_service, "store", {"kp_settings": {"notify_whatsapp_numbers": STAFF}}
    )


async def test_draft_card_tells_request_matches_and_gaps(env):
    quote = await _draft(
        summary="Ввод в частный дом, монтаж на следующей неделе",
        flags=["«АВР 630А» × 1: точного совпадения в каталоге нет — подобрать вручную"],
        items=[{**ITEMS[0], "query": "кабель кг 70"}],
    )
    card, attached = env["notified"][-1]
    assert attached["id"] == quote["id"]
    assert "Что просит клиент:\nВвод в частный дом" in card
    assert "Кабель КГ-хл 1х70 (арт. 02008001) — 30 × 9 483 = 284 490 ₸" in card
    assert "по запросу «кабель кг 70»" in card
    assert "⚠ Не вошло в КП:\n• «АВР 630А»" in card
    # the client text is shown with a readable link marker, not the placeholder
    assert messenger.LINK_LABEL in card and "{link}" not in card
    # the draft opens in the PIM — over https, the PIM hands out http links
    pim = f"https://ar-gs.ru/commercial-offers/edit/{quote['pim_id']}"
    assert f"Открыть в ПИМ: {pim}" in card
    buttons = [b for row in messenger.telegram_keyboard(quote)["inline_keyboard"] for b in row]
    assert {"text": "📄 Открыть в ПИМ", "url": pim} in buttons


def test_parse_command():
    assert messenger.parse_command("ок 18") == ("approve", "18", "")
    assert messenger.parse_command("ОК КП-0018") == ("approve", "0018", "")
    assert messenger.parse_command("отправить") == ("approve", None, "")
    assert messenger.parse_command("отмена 18") == ("reject", "18", "")
    assert messenger.parse_command("текст 18: Добрый день!\n{link}") == (
        "edit",
        "18",
        "Добрый день!\n{link}",
    )
    assert messenger.parse_command("кп") == ("list", None, "")
    # ordinary words are not commands
    assert messenger.parse_command("нет") is None
    assert messenger.parse_command("ок, а что с доставкой?") is None


async def test_client_number_is_not_staff(env):
    _staff_settings(env)
    assert await messenger.handle_staff_whatsapp(PHONE, PHONE, "ок 18") == {"handled": False}


async def test_staff_approves_from_whatsapp(env):
    _staff_settings(env)
    quote = await _draft()
    ref = messenger.quote_ref(quote)

    result = await messenger.handle_staff_whatsapp(STAFF, STAFF, f"ок {ref}")
    assert result["handled"] and result["reply"].startswith("✅")
    after = await kp_service.get_quote(quote["id"])
    assert after["status"] == STATUS_SENT
    assert after["decided_by"] == f"whatsapp:+{STAFF}"
    assert len(env["sent"]) == 1 and LINK in env["sent"][0][3]

    again = await messenger.handle_staff_whatsapp(STAFF, STAFF, f"ок {ref}")
    assert "нет" in again["reply"] and len(env["sent"]) == 1


async def test_staff_edits_then_approves_from_whatsapp(env):
    _staff_settings(env)
    quote = await _draft()
    ref = messenger.quote_ref(quote)

    edited = await messenger.handle_staff_whatsapp(
        STAFF, None, f"текст {ref}: Азамат, ваше КП: {messenger.LINK_LABEL}"
    )
    assert edited["reply"].startswith("✏️") and f"«ок {ref}»" in edited["reply"]
    assert env["sent"] == []  # editing never sends by itself

    await messenger.handle_staff_whatsapp(STAFF, None, "ок")  # the only pending one
    assert env["sent"][0][3] == f"Азамат, ваше КП: {LINK}"


async def test_staff_rejects_and_chatter_is_not_passed_to_assistant(env):
    _staff_settings(env)
    quote = await _draft()

    hello = await messenger.handle_staff_whatsapp(STAFF, STAFF, "Привет, что там по заказам?")
    assert hello["handled"] and quote["number"] in hello["reply"]

    result = await messenger.handle_staff_whatsapp(STAFF, STAFF, "отмена")
    assert result["reply"].startswith("❌")
    assert (await kp_service.get_quote(quote["id"]))["status"] == "rejected"
    assert env["sent"] == []


async def test_telegram_buttons_act_only_from_the_notification_chat(env, monkeypatch):
    quote = await _draft()
    calls: list[tuple[str, dict]] = []

    async def fake_call(token, method, payload, timeout=15):
        calls.append((method, payload))
        return {"message_id": 999}

    monkeypatch.setattr(messenger, "telegram_call", fake_call)

    def press(chat_id, action):
        return {
            "callback_query": {
                "id": "cb1",
                "from": {"username": "director"},
                "data": f"kp:{action}:{quote['id']}",
                "message": {"message_id": 5, "chat": {"id": chat_id}},
            }
        }

    await messenger.handle_telegram_update(press(-100, "approve"), "T", "-200")
    assert calls == [] and env["sent"] == []

    await messenger.handle_telegram_update(press(-200, "edit"), "T", "-200")
    prompt = calls[-1][1]["text"]
    assert f"КП #{quote['id']}" in prompt

    reply = {
        "message": {
            "message_id": 6,
            "chat": {"id": -200},
            "from": {"username": "director"},
            "text": "Новый текст",
            "reply_to_message": {"text": prompt},
        }
    }
    await messenger.handle_telegram_update(reply, "T", "-200")
    card = [p for m, p in calls if m == "sendMessage" and "reply_markup" in p][-1]
    assert "Новый текст" in card["text"]
    assert card["reply_markup"]["inline_keyboard"][0][0]["callback_data"].startswith("kp:approve")

    await messenger.handle_telegram_update(press(-200, "approve"), "T", "-200")
    assert env["sent"][0][3] == f"Новый текст\n{LINK}"
    after = await kp_service.get_quote(quote["id"])
    assert after["decided_by"] == "telegram:@director"
    assert ("editMessageReplyMarkup", {"chat_id": "-200", "message_id": 5}) in calls


async def test_telegram_update_not_ours_falls_through(env, monkeypatch):
    calls: list = []

    async def fake_call(token, method, payload, timeout=15):
        calls.append(method)
        return {}

    monkeypatch.setattr(messenger, "telegram_call", fake_call)
    chatter = {"message": {"message_id": 1, "chat": {"id": -200}, "text": "Добрый день"}}
    other_chat = {"message": {"message_id": 1, "chat": {"id": 42}, "text": "ок 18"}}
    # a client's «ок» in the sales bot must reach the assistant, not vanish
    assert await messenger.handle_telegram_update(chatter, "T", "-200") is False
    assert await messenger.handle_telegram_update(other_chat, "T", "-200") is False
    assert calls == []


async def test_poller_leaves_a_token_its_bot_process_polls(env, monkeypatch):
    import db.database
    from modules.channels.telegram.models import BotInstance

    monkeypatch.setattr(db.database, "AsyncSessionLocal", env["factory"])
    async with env["factory"]() as s:
        s.add(BotInstance(id="tg-main", name="main", bot_token="123:abc", enabled=True))
        await s.commit()
    assert await messenger.token_runs_as_bot("123:abc") is True
    assert await messenger.token_runs_as_bot("999:dedicated") is False


async def test_bot_endpoints_refuse_panel_users():
    HTTPException = pytest.importorskip("fastapi").HTTPException

    from auth_manager import User
    from modules.kp import router as kp_router

    panel_admin = User(id=1, username="admin", role="admin")
    with pytest.raises(HTTPException) as e:
        await kp_router.kp_staff_message(
            kp_router.StaffMessageRequest(sender=STAFF, text="ок 18"), user=panel_admin
        )
    assert e.value.status_code == 403
    with pytest.raises(HTTPException):
        await kp_router.kp_telegram_update(
            kp_router.TelegramUpdateRequest(update={}), user=panel_admin
        )
