"""Tests for KnowledgeUpdated event and FAQ reload handler."""

from unittest.mock import AsyncMock, MagicMock, patch

from modules.core.events import EventBus
from modules.knowledge.events import KnowledgeUpdated
from modules.llm.startup import setup_llm_event_subscriptions


async def test_faq_reload_on_knowledge_updated():
    """FAQ cache reloaded when KnowledgeUpdated(kind='faq') is published."""
    bus = EventBus()
    await setup_llm_event_subscriptions(bus)

    mock_llm = MagicMock()
    mock_llm.reload_faq = MagicMock()
    mock_container = MagicMock()
    mock_container.llm_service = mock_llm

    mock_faq_service = AsyncMock()
    mock_faq_service.get_all = AsyncMock(return_value={"hello": "world"})

    with (
        patch("app.dependencies.get_container", return_value=mock_container),
        patch("modules.knowledge.service.faq_service", mock_faq_service),
    ):
        await bus.publish(KnowledgeUpdated(kind="faq", action="created"))

    mock_faq_service.get_all.assert_awaited_once()
    mock_llm.reload_faq.assert_called_once_with({"hello": "world"})


async def test_non_faq_knowledge_updated_ignored():
    """KnowledgeUpdated with kind != 'faq' does not trigger FAQ reload."""
    bus = EventBus()
    await setup_llm_event_subscriptions(bus)

    mock_llm = MagicMock()
    mock_container = MagicMock()
    mock_container.llm_service = mock_llm

    with patch("app.dependencies.get_container", return_value=mock_container):
        await bus.publish(KnowledgeUpdated(kind="wiki", action="updated"))

    mock_llm.reload_faq.assert_not_called()


async def test_knowledge_updated_event_has_fields():
    event = KnowledgeUpdated(kind="faq", action="deleted", item_id=42)
    assert event.kind == "faq"
    assert event.action == "deleted"
    assert event.item_id == 42
    assert event.timestamp > 0
