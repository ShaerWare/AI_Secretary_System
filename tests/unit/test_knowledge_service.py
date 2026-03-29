"""Tests for KnowledgeService facade.

Verifies that:
- KnowledgeServiceImpl satisfies the Protocol structurally
- All Protocol methods exist with correct signatures
- Converter helpers produce correct TypedDict shapes
"""

import inspect

from modules.knowledge.facade import (
    KnowledgeServiceImpl,
    _to_collection_info,
    _to_document_info,
    _to_faq_entry_info,
    _to_search_result,
)
from modules.knowledge.protocols import KnowledgeService as KnowledgeServiceProtocol


class TestKnowledgeServiceProtocolCompliance:
    """Verify KnowledgeServiceImpl matches the Protocol."""

    def test_has_all_protocol_methods(self):
        """KnowledgeServiceImpl must implement every method from the Protocol."""
        protocol_methods = {
            name
            for name, _ in inspect.getmembers(KnowledgeServiceProtocol, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        impl_methods = {
            name
            for name in dir(KnowledgeServiceImpl)
            if not name.startswith("_") and callable(getattr(KnowledgeServiceImpl, name))
        }
        missing = protocol_methods - impl_methods
        assert not missing, f"KnowledgeServiceImpl missing Protocol methods: {missing}"

    def test_search_signature(self):
        sig = inspect.signature(KnowledgeServiceImpl.search)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "query" in params
        assert "collection_ids" in params
        assert "top_k" in params
        assert "max_chars" in params

    def test_retrieve_context_signature(self):
        sig = inspect.signature(KnowledgeServiceImpl.retrieve_context)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "query" in params
        assert "collection_ids" in params
        assert "top_k" in params
        assert "max_chars" in params

    def test_get_collections_signature(self):
        sig = inspect.signature(KnowledgeServiceImpl.get_collections)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "enabled_only" in params
        assert "workspace_id" in params

    def test_get_collection_signature(self):
        sig = inspect.signature(KnowledgeServiceImpl.get_collection)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "collection_id" in params
        assert "workspace_id" in params

    def test_get_documents_signature(self):
        sig = inspect.signature(KnowledgeServiceImpl.get_documents)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "collection_id" in params
        assert "workspace_id" in params

    def test_sync_documents_signature(self):
        sig = inspect.signature(KnowledgeServiceImpl.sync_documents)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "collection_id" in params
        assert "base_dir" in params

    def test_find_faq_answer_signature(self):
        sig = inspect.signature(KnowledgeServiceImpl.find_faq_answer)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "question" in params

    def test_get_faq_entries_signature(self):
        sig = inspect.signature(KnowledgeServiceImpl.get_faq_entries)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "workspace_id" in params


class TestConverters:
    """Test TypedDict converter helpers."""

    def test_to_search_result(self):
        data = {
            "title": "Installation",
            "body": "Run pip install...",
            "source_file": "docs/install.md",
            "score": 0.85,
            "engine": "bm25",
        }
        result = _to_search_result(data)
        assert result["title"] == "Installation"
        assert result["body"] == "Run pip install..."
        assert result["source_file"] == "docs/install.md"
        assert result["score"] == 0.85
        assert result["collection_id"] is None

    def test_to_search_result_defaults(self):
        result = _to_search_result({})
        assert result["title"] == ""
        assert result["body"] == ""
        assert result["score"] == 0.0
        assert result["collection_id"] is None

    def test_to_collection_info(self):
        data = {
            "id": 1,
            "name": "Default",
            "slug": "default",
            "description": "Default collection",
            "enabled": True,
            "base_dir": "wiki-pages",
            "document_count": 5,
            "created": "2026-01-01T00:00:00",
            "updated": "2026-01-02T00:00:00",
        }
        info = _to_collection_info(data)
        assert info["id"] == 1
        assert info["name"] == "Default"
        assert info["slug"] == "default"
        assert info["document_count"] == 5
        assert info["enabled"] is True

    def test_to_collection_info_defaults(self):
        data = {"id": 2, "name": "Test"}
        info = _to_collection_info(data)
        assert info["slug"] == ""
        assert info["description"] is None
        assert info["base_dir"] == "wiki-pages"
        assert info["document_count"] == 0

    def test_to_document_info(self):
        data = {
            "id": 10,
            "filename": "Architecture.md",
            "title": "Architecture",
            "source_type": "wiki",
            "file_size_bytes": 12345,
            "section_count": 8,
            "collection_id": 1,
            "created": "2026-01-01T00:00:00",
            "updated": None,
        }
        info = _to_document_info(data)
        assert info["id"] == 10
        assert info["filename"] == "Architecture.md"
        assert info["source_type"] == "wiki"
        assert info["file_size_bytes"] == 12345
        assert info["collection_id"] == 1

    def test_to_document_info_defaults(self):
        data = {"id": 11, "filename": "test.md"}
        info = _to_document_info(data)
        assert info["title"] == ""
        assert info["source_type"] == "manual"
        assert info["file_size_bytes"] == 0
        assert info["section_count"] == 0
        assert info["collection_id"] is None

    def test_to_faq_entry_info(self):
        data = {
            "id": 1,
            "question": "What is this?",
            "answer": "An AI secretary",
            "keywords": ["ai", "secretary"],
            "enabled": True,
            "hit_count": 42,
            "created": "2026-01-01T00:00:00",
            "updated": "2026-02-01T00:00:00",
        }
        info = _to_faq_entry_info(data)
        assert info["id"] == 1
        assert info["question"] == "What is this?"
        assert info["answer"] == "An AI secretary"
        assert info["keywords"] == ["ai", "secretary"]
        assert info["hit_count"] == 42

    def test_to_faq_entry_info_defaults(self):
        data = {"id": 2, "question": "?", "answer": "!"}
        info = _to_faq_entry_info(data)
        assert info["keywords"] == []
        assert info["enabled"] is True
        assert info["hit_count"] == 0
        assert info["created"] is None


class TestModuleSingleton:
    """Verify module-level singleton behavior."""

    def test_singleton_initially_none(self):
        from modules.knowledge.facade import knowledge_service

        # Before startup, singleton is None (no container yet)
        # After startup via init_wiki_rag, it becomes KnowledgeServiceImpl
        assert knowledge_service is None or isinstance(knowledge_service, KnowledgeServiceImpl)
