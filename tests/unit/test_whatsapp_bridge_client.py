"""Tests for the self-hosted WhatsApp provider client."""

import hashlib
import hmac

import pytest

from whatsapp_bot.services import choices
from whatsapp_bot.services.bridge_client import BridgeClient, _render_menu


TOKEN = "s3cr3t-bridge-token"


@pytest.fixture
def client():
    return BridgeClient(
        session_id="support-wa", bridge_url="http://127.0.0.1:8005/", bridge_token=TOKEN
    )


@pytest.fixture(autouse=True)
def _clean_registry():
    choices.reset()
    yield
    choices.reset()


# ─── Menu rendering ────────────────────────────────────────────


def test_render_menu_numbers_options():
    text = _render_menu(
        "Что дальше?",
        [{"id": "a", "title": "Демо"}, {"id": "b", "title": "Цены"}],
    )
    assert "Что дальше?" in text
    assert "*1.* Демо" in text
    assert "*2.* Цены" in text


def test_render_menu_includes_header_footer_and_hint():
    text = _render_menu(
        "Body",
        [{"id": "a", "title": "One"}],
        header="Заголовок",
        footer="Подвал",
    )
    assert "*Заголовок*" in text
    assert "_Подвал_" in text
    assert "Ответьте номером" in text


def test_render_menu_numbers_continuously_across_sections():
    """Section grouping must not restart numbering — replies are a single number."""
    options = [
        {"id": "a", "title": "A"},
        {"id": "b", "title": "B"},
        {"id": "c", "title": "C"},
    ]
    text = _render_menu("Body", options, groups=[("Первая", [0, 1]), ("Вторая", [2])])
    assert "*Первая*" in text
    assert "*1.* A" in text
    assert "*2.* B" in text
    assert "*Вторая*" in text
    assert "*3.* C" in text


def test_render_menu_shows_row_description():
    text = _render_menu("Body", [{"id": "a", "title": "Тариф", "description": "от 5000₽"}])
    assert "_от 5000₽_" in text


# ─── Provider interface parity ─────────────────────────────────


def test_exposes_the_cloud_client_interface(client):
    """Handlers call these blind — a missing one is a runtime AttributeError."""
    for method in (
        "send_text",
        "send_buttons",
        "send_list",
        "send_media",
        "send_template",
        "mark_as_read",
        "verify_webhook_signature",
        "close",
    ):
        assert callable(getattr(client, method)), f"BridgeClient is missing {method}"


def test_base_url_trailing_slash_is_normalized(client):
    assert client.bridge_url == "http://127.0.0.1:8005"


# ─── Relink safety ─────────────────────────────────────────────


async def test_start_session_does_not_force_by_default(client, monkeypatch):
    """An automatic (re)start must never discard a working or dead credential set.

    A crash-looping bot calling start() repeatedly would otherwise wipe the link
    or hammer WhatsApp with logins it answers 401 to.
    """
    sent: dict = {}

    async def fake_request(method, path, **kwargs):
        sent["path"] = path
        sent["json"] = kwargs.get("json")
        return {}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.start_session("http://127.0.0.1:8003/bridge/webhook")

    assert sent["path"] == "/start"
    assert sent["json"]["force"] is False


async def test_start_session_forwards_force(client, monkeypatch):
    """The admin "link phone" button asks explicitly, so it may start fresh."""
    sent: dict = {}

    async def fake_request(method, path, **kwargs):
        sent["json"] = kwargs.get("json")
        return {}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.start_session("http://127.0.0.1:8003/bridge/webhook", force=True)

    assert sent["json"]["force"] is True


# ─── Sending registers the menu ────────────────────────────────


async def test_send_buttons_registers_choices(client, monkeypatch):
    sent: dict = {}

    async def fake_send_text(to: str, text: str):
        sent["to"], sent["text"] = to, text
        return {"message_id": "x"}

    monkeypatch.setattr(client, "send_text", fake_send_text)

    await client.send_buttons(
        "79001234567",
        "Выберите",
        [{"id": "sales:demo", "title": "Демо"}, {"id": "nav:menu", "title": "Меню"}],
    )

    # What the user sees and what we resolve against must agree.
    assert "*1.* Демо" in sent["text"]
    assert choices.resolve("79001234567", "1") == ("button_reply", "sales:demo")


async def test_send_list_registers_choices_across_sections(client, monkeypatch):
    async def fake_send_text(to: str, text: str):
        return {"message_id": "x"}

    monkeypatch.setattr(client, "send_text", fake_send_text)

    await client.send_list(
        "79001234567",
        "Выберите",
        "Открыть",
        [
            {"title": "Продукт", "rows": [{"id": "faq:what", "title": "Что это"}]},
            {"title": "Цены", "rows": [{"id": "faq:price", "title": "Сколько стоит"}]},
        ],
    )

    assert choices.resolve("79001234567", "2") == ("list_reply", "faq:price")


async def test_send_buttons_without_options_falls_back_to_text(client, monkeypatch):
    sent: dict = {}

    async def fake_send_text(to: str, text: str):
        sent["text"] = text
        return {}

    monkeypatch.setattr(client, "send_text", fake_send_text)

    await client.send_buttons("79001234567", "Просто текст", [])

    assert sent["text"] == "Просто текст"
    assert choices.resolve("79001234567", "1") is None


# ─── Webhook signature ─────────────────────────────────────────


def test_verify_webhook_signature_accepts_valid(client):
    body = b'{"event":"message"}'
    signature = "sha256=" + hmac.new(TOKEN.encode(), body, hashlib.sha256).hexdigest()
    assert client.verify_webhook_signature(body, signature) is True


def test_verify_webhook_signature_rejects_tampered_body(client):
    body = b'{"event":"message"}'
    signature = "sha256=" + hmac.new(TOKEN.encode(), body, hashlib.sha256).hexdigest()
    assert client.verify_webhook_signature(b'{"event":"evil"}', signature) is False


@pytest.mark.parametrize("signature", ["", "sha256=deadbeef", "garbage"])
def test_verify_webhook_signature_rejects_bad_values(client, signature):
    assert client.verify_webhook_signature(b"{}", signature) is False


def test_verify_webhook_signature_without_token_is_permissive():
    """Mirrors the Cloud client: no secret configured → no verification."""
    unsecured = BridgeClient(session_id="s", bridge_url="http://x", bridge_token="")
    assert unsecured.verify_webhook_signature(b"{}", "") is True
