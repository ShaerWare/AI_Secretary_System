"""KnowledgeService facade — unified entry point for knowledge retrieval and management.

Implements the ``KnowledgeService`` Protocol from ``modules.knowledge.protocols``.
Delegates to existing services (Strangler Fig pattern):
- Search/retrieval → ``wiki_rag_service`` (via ServiceContainer, lazy)
- Collections → ``KnowledgeCollectionService``
- Documents → ``KnowledgeDocService``
- FAQ → ``FAQService``

Existing singletons (``faq_service``, ``knowledge_collection_service``, etc.)
remain for backward compatibility — this facade wraps them, not replaces.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from modules.knowledge.schemas import (
    CollectionInfo,
    DocumentInfo,
    FAQEntryInfo,
    SearchResult,
    SyncResult,
)


if TYPE_CHECKING:
    from app.dependencies import ServiceContainer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# dict → TypedDict converters
# ---------------------------------------------------------------------------


def _to_search_result(d: dict) -> SearchResult:
    """Convert a wiki_rag search result dict to SearchResult TypedDict."""
    return SearchResult(
        title=d.get("title", ""),
        body=d.get("body", ""),
        source_file=d.get("source_file", ""),
        score=d.get("score", 0.0),
        collection_id=d.get("collection_id"),
    )


def _to_collection_info(d: dict) -> CollectionInfo:
    """Convert a KnowledgeCollectionService dict to CollectionInfo TypedDict."""
    return CollectionInfo(
        id=d["id"],
        name=d["name"],
        slug=d.get("slug", ""),
        description=d.get("description"),
        enabled=d.get("enabled", True),
        base_dir=d.get("base_dir", "wiki-pages"),
        document_count=d.get("document_count", 0),
        created=d.get("created"),
        updated=d.get("updated"),
    )


def _to_document_info(d: dict) -> DocumentInfo:
    """Convert a KnowledgeDocService dict to DocumentInfo TypedDict."""
    return DocumentInfo(
        id=d["id"],
        filename=d["filename"],
        title=d.get("title", ""),
        source_type=d.get("source_type", "manual"),
        file_size_bytes=d.get("file_size_bytes", 0),
        section_count=d.get("section_count", 0),
        collection_id=d.get("collection_id"),
        created=d.get("created"),
        updated=d.get("updated"),
    )


def _to_faq_entry_info(d: dict) -> FAQEntryInfo:
    """Convert a FAQService dict to FAQEntryInfo TypedDict."""
    return FAQEntryInfo(
        id=d["id"],
        question=d["question"],
        answer=d["answer"],
        keywords=d.get("keywords", []),
        enabled=d.get("enabled", True),
        hit_count=d.get("hit_count", 0),
        created=d.get("created"),
        updated=d.get("updated"),
    )


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------


class KnowledgeServiceImpl:
    """Facade implementing the KnowledgeService Protocol.

    Receives ``ServiceContainer`` to lazily access ``wiki_rag_service``
    (initialized later during startup).  CRUD services are imported
    directly from ``modules.knowledge.service``.
    """

    def __init__(self, container: ServiceContainer) -> None:
        self._container = container

    # -- Search ---------------------------------------------------------------

    async def search(
        self,
        query: str,
        *,
        collection_ids: list[int] | None = None,
        top_k: int = 3,
        max_chars: int = 2500,
    ) -> list[SearchResult]:
        """Semantic + BM25 search across indexed documents."""
        wiki_rag = self._container.wiki_rag_service
        if not wiki_rag:
            return []

        if not collection_ids:
            # Global index
            raw = await wiki_rag.search_async(query, top_k=top_k)
        elif len(collection_ids) == 1:
            raw = await wiki_rag.search_async(query, top_k=top_k, collection_id=collection_ids[0])
        else:
            # Multi-collection: search each, merge, deduplicate, sort
            import asyncio

            tasks = [
                wiki_rag.search_async(query, top_k=top_k, collection_id=cid)
                for cid in collection_ids
            ]
            results_per_collection = await asyncio.gather(*tasks)

            # Deduplicate by (source_file, title), keep best score
            seen: dict[tuple[str, str], dict] = {}
            for results in results_per_collection:
                for r in results:
                    key = (r.get("source_file", ""), r.get("title", ""))
                    if key not in seen or r.get("score", 0) > seen[key].get("score", 0):
                        seen[key] = r
            raw = sorted(seen.values(), key=lambda x: x.get("score", 0), reverse=True)[:top_k]

        return [_to_search_result(r) for r in raw]

    async def retrieve_context(
        self,
        query: str,
        *,
        collection_ids: list[int] | None = None,
        top_k: int = 3,
        max_chars: int = 2500,
    ) -> str:
        """Return pre-formatted context string for LLM prompt injection."""
        wiki_rag = self._container.wiki_rag_service
        if not wiki_rag:
            return ""

        if not collection_ids:
            return await wiki_rag.retrieve_async(query, top_k=top_k, max_chars=max_chars)
        elif len(collection_ids) == 1:
            return await wiki_rag.retrieve_async(
                query, top_k=top_k, max_chars=max_chars, collection_id=collection_ids[0]
            )
        else:
            return await wiki_rag.retrieve_multi_async(
                query, collection_ids=collection_ids, top_k=top_k, max_chars=max_chars
            )

    # -- Collections ----------------------------------------------------------

    async def get_collections(
        self,
        *,
        enabled_only: bool = False,
        workspace_id: int | None = None,
    ) -> list[CollectionInfo]:
        """List knowledge collections, optionally filtered."""
        from modules.knowledge.service import knowledge_collection_service

        raw = await knowledge_collection_service.get_all(
            enabled_only=enabled_only, workspace_id=workspace_id
        )
        return [_to_collection_info(c) for c in raw]

    async def get_collection(
        self,
        collection_id: int,
        *,
        workspace_id: int | None = None,
    ) -> CollectionInfo | None:
        """Get a single collection by ID."""
        from modules.knowledge.service import knowledge_collection_service

        raw = await knowledge_collection_service.get_by_id(
            collection_id, workspace_id=workspace_id
        )
        if raw is None:
            return None
        return _to_collection_info(raw)

    # -- Documents ------------------------------------------------------------

    async def get_documents(
        self,
        collection_id: int,
        *,
        workspace_id: int | None = None,
    ) -> list[DocumentInfo]:
        """List documents in a collection."""
        from modules.knowledge.service import knowledge_doc_service

        raw = await knowledge_doc_service.get_by_collection(
            collection_id, workspace_id=workspace_id
        )
        return [_to_document_info(d) for d in raw]

    async def sync_documents(
        self,
        collection_id: int,
        base_dir: str,
    ) -> SyncResult:
        """Re-index documents from disk into the collection."""
        from modules.knowledge.service import knowledge_collection_service

        # Get filenames for this collection
        filenames = await knowledge_collection_service.get_document_filenames(collection_id)

        # Reload RAG index
        wiki_rag = self._container.wiki_rag_service
        sections_indexed = 0
        if wiki_rag:
            cidx = wiki_rag.reload_collection(collection_id, filenames, Path(base_dir))
            if cidx:
                sections_indexed = len(cidx.sections)

        # Sync to Vector Search if available
        vs_client = self._container.vector_search_client
        if vs_client and wiki_rag:
            try:
                from modules.knowledge.tasks import sync_collection_to_vector_search

                collection = await knowledge_collection_service.get_by_id(collection_id)
                slug = collection["slug"] if collection else str(collection_id)
                await sync_collection_to_vector_search(wiki_rag, vs_client, collection_id, slug)
            except Exception as vs_err:
                logger.warning("Vector Search sync failed for collection %d: %s", collection_id, vs_err)

        return SyncResult(
            collection_id=collection_id,
            documents_synced=len(filenames),
            sections_indexed=sections_indexed,
        )

    # -- FAQ ------------------------------------------------------------------

    async def find_faq_answer(self, question: str) -> str | None:
        """BM25-match a user question against FAQ entries."""
        from modules.knowledge.service import faq_service

        return await faq_service.find_answer(question)

    async def get_faq_entries(
        self,
        *,
        workspace_id: int | None = None,
    ) -> list[FAQEntryInfo]:
        """List all FAQ entries."""
        from modules.knowledge.service import faq_service

        raw = await faq_service.get_all_entries(workspace_id=workspace_id)
        return [_to_faq_entry_info(e) for e in raw]


# Module-level singleton — NOT created here because it needs ServiceContainer.
# Created in startup and set via: knowledge_service_impl = KnowledgeServiceImpl(container)
knowledge_service: Optional[KnowledgeServiceImpl] = None
