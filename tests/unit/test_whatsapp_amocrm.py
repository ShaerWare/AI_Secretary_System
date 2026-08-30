"""Tests for the WhatsApp → amoCRM lead/notes wiring.

The WhatsApp bot is a separate process with no access to the in-process
EventBus, so its CRM events are published by the orchestrator's chat router.
That is only possible because sessions now carry ``source="whatsapp"`` and a
per-sender ``source_id``; these tests pin both the parsing of that identity and
the guards that keep a duplicate lead (or a CRM outage) from reaching a client.

Publishing is fire-and-forget via ``asyncio.create_task``, so every test yields
to the loop once before asserting on awaits.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from modules.channels.whatsapp.events import WhatsAppMessageSent, WhatsAppSessionCreated
from modules.chat.router import (
    _publish_whatsapp_session_created,
    _publish_whatsapp_turn,
    _whatsapp_sender,
)


def _session(**over) -> dict:
    base = {
        "id": "chat_1",
        "source": "whatsapp",
        "source_id": "wa-77085442089:77012345678",
        "amocrm_lead_id": None,
    }
    base.update(over)
    return base


class _Bus:
    """Container stub exposing an AsyncMock event bus."""

    def __init__(self) -> None:
        self.event_bus = AsyncMock()


class TestSenderParsing:
    def test_splits_instance_and_sender(self):
        assert _whatsapp_sender(_session()) == ("wa-77085442089", "77012345678")

    def test_lid_sender_is_kept_verbatim(self):
        parsed = _whatsapp_sender(_session(source_id="wa-1:106334968131631@lid"))
        assert parsed == ("wa-1", "106334968131631@lid")

    @pytest.mark.parametrize(
        "session",
        [
            {"id": "c", "source": "widget", "source_id": "w-1:x"},
            {"id": "c", "source": "telegram_bot", "source_id": "b-1:42"},
            {"id": "c", "source": "whatsapp", "source_id": ""},
            {"id": "c", "source": "whatsapp", "source_id": "no-colon"},
            {"id": "c", "source": "whatsapp", "source_id": ":77012345678"},
            {"id": "c", "source": "whatsapp", "source_id": "wa-1:"},
        ],
    )
    def test_non_whatsapp_or_malformed_yields_nothing(self, session):
        assert _whatsapp_sender(session) is None


class TestSessionCreatedPublishing:
    async def test_publishes_for_a_fresh_whatsapp_session(self):
        bus = _Bus()
        with patch("modules.chat.router.get_container", return_value=bus):
            lead_id = await _publish_whatsapp_session_created(_session(), "Здравствуйте")
            await asyncio.sleep(0)

        assert lead_id == 0
        bus.event_bus.publish.assert_awaited_once()
        event = bus.event_bus.publish.await_args.args[0]
        assert isinstance(event, WhatsAppSessionCreated)
        assert event.instance_id == "wa-77085442089"
        assert event.sender == "77012345678"
        assert event.first_message == "Здравствуйте"

    async def test_existing_lead_is_returned_and_not_republished(self):
        # Otherwise every message from a known client opens another lead.
        bus = _Bus()
        with patch("modules.chat.router.get_container", return_value=bus):
            lead_id = await _publish_whatsapp_session_created(
                _session(amocrm_lead_id=555), "снова здравствуйте"
            )
            await asyncio.sleep(0)

        assert lead_id == 555
        bus.event_bus.publish.assert_not_awaited()

    async def test_other_channels_are_untouched(self):
        bus = _Bus()
        with patch("modules.chat.router.get_container", return_value=bus):
            lead_id = await _publish_whatsapp_session_created(_session(source="widget"), "привет")
            await asyncio.sleep(0)

        assert lead_id == 0
        bus.event_bus.publish.assert_not_awaited()


class TestTurnPublishing:
    async def test_publishes_a_completed_turn(self):
        bus = _Bus()
        with patch("modules.chat.router.get_container", return_value=bus):
            _publish_whatsapp_turn(_session(), 555, "есть ЧРП?", "Да, подскажу модель")
            await asyncio.sleep(0)

        bus.event_bus.publish.assert_awaited_once()
        event = bus.event_bus.publish.await_args.args[0]
        assert isinstance(event, WhatsAppMessageSent)
        assert event.lead_id == 555
        assert event.sender == "77012345678"
        assert event.assistant_response == "Да, подскажу модель"

    @pytest.mark.parametrize(
        ("lead_id", "response"),
        [
            (0, "ответ"),  # lead not created yet — nowhere to file the note
            (555, ""),  # generation produced nothing
        ],
    )
    async def test_nothing_published_without_lead_or_answer(self, lead_id, response):
        bus = _Bus()
        with patch("modules.chat.router.get_container", return_value=bus):
            _publish_whatsapp_turn(_session(), lead_id, "вопрос", response)
            await asyncio.sleep(0)

        bus.event_bus.publish.assert_not_awaited()

    async def test_other_channels_are_untouched(self):
        bus = _Bus()
        with patch("modules.chat.router.get_container", return_value=bus):
            _publish_whatsapp_turn(_session(source="admin"), 555, "вопрос", "ответ")
            await asyncio.sleep(0)

        bus.event_bus.publish.assert_not_awaited()
