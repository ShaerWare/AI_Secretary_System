"""The own-product funnel is opt-in per WhatsApp instance.

It used to be hardcoded, so a client's assistant answered their customers'
"привет" with a pitch for AI Secretary (and a numbered menu of our product
FAQ). Only our own marketing numbers may run it.
"""

from types import SimpleNamespace

import pytest

from whatsapp_bot.state import get_bot_config, sales_funnel_enabled, set_bot_config


def _config(sales_funnel_enabled: bool = False) -> SimpleNamespace:
    """Stand-in for WhatsAppBotConfig (importing it needs pydantic)."""
    return SimpleNamespace(instance_id="stalker-wa", sales_funnel_enabled=sales_funnel_enabled)


@pytest.fixture(autouse=True)
def _restore_config():
    previous = get_bot_config()
    yield
    set_bot_config(previous)


def test_funnel_off_for_a_client_instance():
    set_bot_config(_config())
    assert sales_funnel_enabled() is False


def test_funnel_on_when_the_instance_opts_in():
    set_bot_config(_config(True))
    assert sales_funnel_enabled() is True


def test_standalone_mode_keeps_the_funnel():
    """`.env` mode is only ever our own bot — mirrors the Telegram bot."""
    set_bot_config(None)
    assert sales_funnel_enabled() is True


async def test_greeting_reaches_the_llm_when_the_funnel_is_off(monkeypatch):
    """ "привет" must be answered by the client's assistant, not by our pitch."""
    pytest.importorskip("pydantic", reason="whatsapp_bot.config needs pydantic")
    from whatsapp_bot.handlers import messages

    set_bot_config(_config())
    sent: list[str] = []
    welcomed: list[str] = []

    class _Client:
        async def mark_as_read(self, message_id):
            return {}

        async def send_text(self, to, text):
            sent.append(text)
            return {}

    class _Router:
        async def chat(self, messages, conversation_key=None):
            return "Здравствуйте! Чем помочь?"

    class _Session:
        messages: list = []

        def append_message(self, role, content):
            self.messages.append({"role": role, "content": content})

    class _Store:
        def get_or_create(self, phone):
            return _Session()

    client, router, store = _Client(), _Router(), _Store()
    monkeypatch.setattr(messages, "get_whatsapp_client", lambda: client)
    monkeypatch.setattr(messages, "get_llm_router", lambda: router)
    monkeypatch.setattr(messages, "get_session_store", lambda: store)

    import whatsapp_bot.handlers.sales.welcome as welcome_mod

    async def _fail(phone):
        welcomed.append(phone)

    monkeypatch.setattr(welcome_mod, "handle_welcome", _fail)

    await messages._process_message("77011112233", "привет", "wamid.1")

    assert welcomed == []
    assert sent == ["Здравствуйте! Чем помочь?"]
