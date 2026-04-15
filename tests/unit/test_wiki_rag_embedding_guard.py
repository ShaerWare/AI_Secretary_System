"""Tests for the Vector Search embedding guard in init_wiki_rag.

Covers the fix in #681: when VECTOR_SEARCH_URL is configured, init_wiki_rag
must skip the inline embedding_provider path entirely and must NOT register
the `wiki-embeddings` task. Context: this project runs on claude_bridge /
OpenRouter, neither of which exposes /v1/embeddings — without the guard,
reload_collection would hang retrying 404s. The dedicated Vector Search
microservice owns embeddings in this setup.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from modules.core.tasks import TaskRegistry
from modules.knowledge import startup as knowledge_startup


def _make_container():
    container = SimpleNamespace()
    container.knowledge_service = None
    container.wiki_rag_service = None
    # Mimic the real server setup: claude_bridge-style provider config with
    # no /v1/embeddings endpoint. Included to prove the guard short-circuits
    # BEFORE the code tries to build a cloud provider against it.
    container.llm_service = SimpleNamespace(
        config={
            "provider_type": "claude_bridge",
            "api_key": "fake-key",
            "base_url": "http://localhost:9000/v1",
        }
    )
    return container


@pytest.fixture()
def fake_wiki_rag():
    """Patch WikiRAGService so we don't touch the filesystem."""
    rag = MagicMock(name="WikiRAGService")
    with patch("app.services.wiki_rag_service.WikiRAGService", return_value=rag) as cls:
        yield rag, cls


async def test_vector_search_configured_skips_embedding_providers(monkeypatch, fake_wiki_rag):
    """With VECTOR_SEARCH_URL set, no embedding provider is wired up."""
    rag, _ = fake_wiki_rag
    monkeypatch.setenv("VECTOR_SEARCH_URL", "http://localhost:8003")

    container = _make_container()
    registry = TaskRegistry()

    await knowledge_startup.init_wiki_rag(container, "full", registry)

    rag.set_embedding_provider.assert_not_called()
    task_names = {t.name for t in registry.list_tasks()}
    assert "wiki-embeddings" not in task_names
    # The collection-index loader is unrelated and must still be registered.
    assert "wiki-collection-indexes" in task_names


async def test_without_guard_legacy_path_wires_broken_provider(monkeypatch, fake_wiki_rag):
    """Regression witness: without VECTOR_SEARCH_URL, init_wiki_rag happily
    builds an OpenAIEmbeddingProvider against claude_bridge — which has no
    /v1/embeddings endpoint and will 404 at runtime. This is exactly the
    failure mode #681 prevents; keeping a test for it makes it obvious why
    the guard matters and locks the behavioral contract in place."""
    rag, _ = fake_wiki_rag
    monkeypatch.delenv("VECTOR_SEARCH_URL", raising=False)

    container = _make_container()
    registry = TaskRegistry()

    await knowledge_startup.init_wiki_rag(container, "cloud", registry)

    rag.set_embedding_provider.assert_called_once()
    task_names = {t.name for t in registry.list_tasks()}
    assert "wiki-embeddings" in task_names
