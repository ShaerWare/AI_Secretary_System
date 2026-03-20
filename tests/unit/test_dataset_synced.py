"""Tests for DatasetSynced event and knowledge reindex handler."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from modules.core.events import DatasetSynced, EventBus
from modules.knowledge.startup import setup_knowledge_event_subscriptions


async def test_dataset_synced_creates_collection_and_docs():
    """Handler creates collection + documents + reloads RAG on sync event."""
    bus = EventBus()
    await setup_knowledge_event_subscriptions(bus)

    mock_collection_svc = AsyncMock()
    mock_collection_svc.get_by_slug = AsyncMock(return_value=None)
    mock_collection_svc.create = AsyncMock(return_value={"id": 42})

    mock_doc_svc = AsyncMock()
    mock_doc_svc.get_by_collection = AsyncMock(return_value=[])
    mock_doc_svc.create = AsyncMock()

    mock_wiki_rag = MagicMock()
    mock_container = MagicMock()
    mock_container.wiki_rag_service = mock_wiki_rag

    documents = [
        {
            "filename": "crm-pipeline-1.md",
            "title": "Pipeline 1",
            "source_type": "amocrm",
            "file_size_bytes": 100,
            "section_count": 3,
        },
        {
            "filename": "crm-summary.md",
            "title": "Summary",
            "source_type": "amocrm",
            "file_size_bytes": 200,
            "section_count": 5,
        },
    ]

    with (
        patch(
            "modules.knowledge.service.knowledge_collection_service",
            mock_collection_svc,
        ),
        patch("modules.knowledge.service.knowledge_doc_service", mock_doc_svc),
        patch("app.dependencies.get_container", return_value=mock_container),
    ):
        await bus.publish(
            DatasetSynced(
                source="amocrm",
                collection_slug="amocrm",
                action="synced",
                collection_name="amoCRM",
                collection_description="CRM data",
                base_dir="data/crm-dataset",
                documents=documents,
            )
        )

    mock_collection_svc.get_by_slug.assert_awaited_once_with("amocrm")
    mock_collection_svc.create.assert_awaited_once()
    assert mock_doc_svc.create.await_count == 2
    mock_wiki_rag.reload_collection.assert_called_once_with(
        42, ["crm-pipeline-1.md", "crm-summary.md"], Path("data/crm-dataset")
    )


async def test_dataset_synced_reuses_existing_collection():
    """Handler reuses existing collection and deletes old docs before creating new ones."""
    bus = EventBus()
    await setup_knowledge_event_subscriptions(bus)

    mock_collection_svc = AsyncMock()
    mock_collection_svc.get_by_slug = AsyncMock(return_value={"id": 7})

    mock_doc_svc = AsyncMock()
    mock_doc_svc.get_by_collection = AsyncMock(return_value=[{"id": 10}, {"id": 11}])
    mock_doc_svc.delete = AsyncMock()
    mock_doc_svc.create = AsyncMock()

    mock_container = MagicMock()
    mock_container.wiki_rag_service = None

    with (
        patch(
            "modules.knowledge.service.knowledge_collection_service",
            mock_collection_svc,
        ),
        patch("modules.knowledge.service.knowledge_doc_service", mock_doc_svc),
        patch("app.dependencies.get_container", return_value=mock_container),
    ):
        await bus.publish(
            DatasetSynced(
                source="woocommerce",
                collection_slug="woocommerce",
                action="synced",
                base_dir="data/wc-dataset",
                documents=[
                    {
                        "filename": "wc-summary.md",
                        "title": "WC Summary",
                        "source_type": "woocommerce",
                    }
                ],
            )
        )

    mock_collection_svc.create.assert_not_awaited()
    assert mock_doc_svc.delete.await_count == 2
    mock_doc_svc.create.assert_awaited_once()


async def test_dataset_cleared_deletes_docs_and_reloads_rag():
    """Handler deletes docs and reloads RAG with empty list on clear event."""
    bus = EventBus()
    await setup_knowledge_event_subscriptions(bus)

    mock_collection_svc = AsyncMock()
    mock_collection_svc.get_by_slug = AsyncMock(return_value={"id": 5})

    mock_doc_svc = AsyncMock()
    mock_doc_svc.get_by_collection = AsyncMock(return_value=[{"id": 1}])
    mock_doc_svc.delete = AsyncMock()

    mock_wiki_rag = MagicMock()
    mock_container = MagicMock()
    mock_container.wiki_rag_service = mock_wiki_rag

    with (
        patch(
            "modules.knowledge.service.knowledge_collection_service",
            mock_collection_svc,
        ),
        patch("modules.knowledge.service.knowledge_doc_service", mock_doc_svc),
        patch("app.dependencies.get_container", return_value=mock_container),
    ):
        await bus.publish(
            DatasetSynced(
                source="amocrm",
                collection_slug="amocrm",
                action="cleared",
                base_dir="data/crm-dataset",
            )
        )

    mock_doc_svc.delete.assert_awaited_once_with(1)
    mock_wiki_rag.reload_collection.assert_called_once_with(5, [], Path("data/crm-dataset"))
    mock_collection_svc.delete.assert_not_awaited()


async def test_dataset_cleared_with_delete_collection():
    """Handler deletes collection record when delete_collection=True."""
    bus = EventBus()
    await setup_knowledge_event_subscriptions(bus)

    mock_collection_svc = AsyncMock()
    mock_collection_svc.get_by_slug = AsyncMock(return_value={"id": 9})
    mock_collection_svc.delete = AsyncMock()

    mock_doc_svc = AsyncMock()
    mock_doc_svc.get_by_collection = AsyncMock(return_value=[])

    mock_wiki_rag = MagicMock()
    mock_container = MagicMock()
    mock_container.wiki_rag_service = mock_wiki_rag

    with (
        patch(
            "modules.knowledge.service.knowledge_collection_service",
            mock_collection_svc,
        ),
        patch("modules.knowledge.service.knowledge_doc_service", mock_doc_svc),
        patch("app.dependencies.get_container", return_value=mock_container),
    ):
        await bus.publish(
            DatasetSynced(
                source="kanban",
                collection_slug="kanban-owner-repo",
                action="cleared",
                base_dir="data/kanban-dataset",
                delete_collection=True,
            )
        )

    mock_wiki_rag.unload_collection.assert_called_once_with(9)
    mock_collection_svc.delete.assert_awaited_once_with(9)


async def test_dataset_cleared_noop_when_collection_missing():
    """Handler does nothing if collection doesn't exist on clear."""
    bus = EventBus()
    await setup_knowledge_event_subscriptions(bus)

    mock_collection_svc = AsyncMock()
    mock_collection_svc.get_by_slug = AsyncMock(return_value=None)

    mock_doc_svc = AsyncMock()

    with (
        patch(
            "modules.knowledge.service.knowledge_collection_service",
            mock_collection_svc,
        ),
        patch("modules.knowledge.service.knowledge_doc_service", mock_doc_svc),
    ):
        await bus.publish(
            DatasetSynced(
                source="amocrm",
                collection_slug="amocrm",
                action="cleared",
            )
        )

    mock_doc_svc.get_by_collection.assert_not_awaited()


async def test_dataset_synced_event_fields():
    """DatasetSynced event has all expected fields."""
    event = DatasetSynced(
        source="woocommerce",
        collection_slug="woocommerce",
        action="synced",
        collection_name="WooCommerce",
        collection_description="WC data",
        base_dir="/data/wc",
        documents=[{"filename": "test.md"}],
        delete_collection=False,
    )
    assert event.source == "woocommerce"
    assert event.collection_slug == "woocommerce"
    assert event.action == "synced"
    assert event.collection_name == "WooCommerce"
    assert len(event.documents) == 1
    assert event.timestamp > 0
