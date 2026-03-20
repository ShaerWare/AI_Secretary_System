"""Tests for Widget → CRM event handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

from modules.channels.widget.events import (
    WidgetContactSubmitted,
    WidgetMessageSent,
    WidgetSessionCreated,
)
from modules.core.events import EventBus
from modules.crm.startup import setup_crm_event_subscriptions

# Patch target for amoCRM API functions (lazy-imported as module in handlers)
_AMO = "app.services.amocrm_service"


async def test_widget_session_created_creates_lead():
    """WidgetSessionCreated creates amoCRM lead and saves lead_id to session."""
    bus = EventBus()
    await setup_crm_event_subscriptions(bus)

    mock_config = {
        "access_token": "tok",
        "subdomain": "test",
        "auto_create_lead": True,
        "lead_pipeline_id": 1,
        "lead_status_id": 2,
    }

    with (
        patch(
            "modules.crm.service.amocrm_service.get_config_with_secrets",
            AsyncMock(return_value=mock_config),
        ),
        patch(f"{_AMO}.create_lead", AsyncMock(return_value={"_embedded": {"leads": [{"id": 777}]}})) as mock_create,
        patch(f"{_AMO}.add_note_to_lead", AsyncMock()) as mock_note,
        patch("modules.crm.startup._save_session_field", AsyncMock()) as mock_save,
    ):
        await bus.publish(
            WidgetSessionCreated(
                session_id="sess-123",
                first_message="Привет!",
                visitor_metadata={"page_url": "https://example.com", "ip": "1.2.3.4"},
            )
        )

    mock_create.assert_awaited_once()
    mock_save.assert_awaited_once_with("sess-123", amocrm_lead_id=777)
    mock_note.assert_awaited_once()
    note_text = mock_note.call_args[0][3]
    assert "Привет!" in note_text
    assert "https://example.com" in note_text


async def test_widget_session_created_skips_when_auto_create_disabled():
    """WidgetSessionCreated does nothing when auto_create_lead is disabled."""
    bus = EventBus()
    await setup_crm_event_subscriptions(bus)

    mock_config = {
        "access_token": "tok",
        "subdomain": "test",
        "auto_create_lead": False,
    }

    with (
        patch(
            "modules.crm.service.amocrm_service.get_config_with_secrets",
            AsyncMock(return_value=mock_config),
        ),
        patch(f"{_AMO}.create_lead", AsyncMock()) as mock_create,
    ):
        await bus.publish(WidgetSessionCreated(session_id="sess-456", first_message="Hi"))

    mock_create.assert_not_awaited()


async def test_widget_session_created_skips_when_no_config():
    """WidgetSessionCreated does nothing when amoCRM is not configured."""
    bus = EventBus()
    await setup_crm_event_subscriptions(bus)

    with patch(
        "modules.crm.service.amocrm_service.get_config_with_secrets",
        AsyncMock(return_value=None),
    ):
        # Should not raise
        await bus.publish(WidgetSessionCreated(session_id="sess-789", first_message="Hello"))


async def test_widget_message_sent_adds_note():
    """WidgetMessageSent appends conversation turn as note to lead."""
    bus = EventBus()
    await setup_crm_event_subscriptions(bus)

    mock_config = {"access_token": "tok", "subdomain": "test"}

    with (
        patch(
            "modules.crm.service.amocrm_service.get_config_with_secrets",
            AsyncMock(return_value=mock_config),
        ),
        patch(f"{_AMO}.add_note_to_lead", AsyncMock()) as mock_note,
    ):
        await bus.publish(
            WidgetMessageSent(
                session_id="sess-123",
                lead_id=777,
                user_message="Сколько стоит?",
                assistant_response="От 1000 руб.",
            )
        )

    mock_note.assert_awaited_once()
    args = mock_note.call_args[0]
    assert args[0] == "test"  # subdomain
    assert args[2] == 777  # lead_id
    assert "Сколько стоит?" in args[3]
    assert "От 1000 руб." in args[3]


async def test_widget_contact_submitted_creates_contact_and_links():
    """WidgetContactSubmitted creates contact and links to existing lead."""
    bus = EventBus()
    await setup_crm_event_subscriptions(bus)

    mock_config = {"access_token": "tok", "subdomain": "test"}
    mock_session = {"amocrm_lead_id": 777, "visitor_metadata": {}}

    with (
        patch(
            "modules.crm.service.amocrm_service.get_config_with_secrets",
            AsyncMock(return_value=mock_config),
        ),
        patch(
            f"{_AMO}.create_contact",
            AsyncMock(return_value={"_embedded": {"contacts": [{"id": 555}]}}),
        ) as mock_create_contact,
        patch(f"{_AMO}.link_contact_to_lead", AsyncMock()) as mock_link,
        patch(f"{_AMO}.add_note_to_lead", AsyncMock()),
        patch("modules.crm.startup._save_session_field", AsyncMock()) as mock_save,
        patch(
            "modules.chat.service.chat_service.get_session",
            AsyncMock(return_value=mock_session),
        ),
    ):
        await bus.publish(
            WidgetContactSubmitted(
                session_id="sess-123",
                contact_name="Иван",
                phone="+79001234567",
                email="ivan@test.com",
            )
        )

    mock_create_contact.assert_awaited_once()
    mock_save.assert_awaited_once_with("sess-123", amocrm_contact_id=555)
    mock_link.assert_awaited_once_with("test", "tok", 777, 555)


async def test_widget_contact_submitted_creates_lead_when_no_existing():
    """WidgetContactSubmitted creates new lead when session has no lead_id."""
    bus = EventBus()
    await setup_crm_event_subscriptions(bus)

    mock_config = {
        "access_token": "tok",
        "subdomain": "test",
        "lead_pipeline_id": 1,
        "lead_status_id": 2,
    }
    mock_session = {"amocrm_lead_id": None, "visitor_metadata": {}}

    with (
        patch(
            "modules.crm.service.amocrm_service.get_config_with_secrets",
            AsyncMock(return_value=mock_config),
        ),
        patch(
            f"{_AMO}.create_contact",
            AsyncMock(return_value={"_embedded": {"contacts": [{"id": 555}]}}),
        ),
        patch(
            f"{_AMO}.create_lead",
            AsyncMock(return_value={"_embedded": {"leads": [{"id": 888}]}}),
        ) as mock_create_lead,
        patch("modules.crm.startup._save_session_field", AsyncMock()) as mock_save,
        patch(
            "modules.chat.service.chat_service.get_session",
            AsyncMock(return_value=mock_session),
        ),
    ):
        await bus.publish(
            WidgetContactSubmitted(
                session_id="sess-456",
                contact_name="Мария",
                phone="+79005556677",
                email="",
            )
        )

    # Should have saved contact_id, then lead_id
    assert mock_save.await_count == 2
    mock_save.assert_any_await("sess-456", amocrm_contact_id=555)
    mock_save.assert_any_await("sess-456", amocrm_lead_id=888)
    mock_create_lead.assert_awaited_once()


async def test_widget_events_have_fields():
    """Widget events have expected fields."""
    e1 = WidgetSessionCreated(
        session_id="s1", first_message="hi", visitor_metadata={"ip": "1.1.1.1"}
    )
    assert e1.session_id == "s1"
    assert e1.first_message == "hi"
    assert e1.visitor_metadata == {"ip": "1.1.1.1"}
    assert e1.timestamp > 0

    e2 = WidgetMessageSent(session_id="s2", lead_id=42, user_message="q", assistant_response="a")
    assert e2.lead_id == 42

    e3 = WidgetContactSubmitted(session_id="s3", contact_name="Test", phone="+7", email="t@t.com")
    assert e3.contact_name == "Test"
    assert e3.phone == "+7"
