"""Target Protocol interfaces for the Knowledge domain.

These Protocols describe the *ideal* service contracts that the
codebase will migrate toward.  Current implementations
(``service.py``, ``wiki_rag_service.py``) do not yet fully conform —
the Protocols serve as an architectural north star.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable


if TYPE_CHECKING:
    from modules.knowledge.schemas import (
        CollectionInfo,
        DocumentInfo,
        FAQEntryInfo,
        SearchResult,
        SyncResult,
    )


@runtime_checkable
class KnowledgeService(Protocol):
    """Unified facade for knowledge retrieval and management.

    Combines search (currently in ``wiki_rag_service.py``) with
    collection/document management (currently in ``service.py``).
    """

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
        ...

    async def retrieve_context(
        self,
        query: str,
        *,
        collection_ids: list[int] | None = None,
        top_k: int = 3,
        max_chars: int = 2500,
    ) -> str:
        """Return pre-formatted context string for LLM prompt injection."""
        ...

    # -- Collections ----------------------------------------------------------

    async def get_collections(
        self,
        *,
        enabled_only: bool = False,
        workspace_id: int | None = None,
    ) -> list[CollectionInfo]:
        """List knowledge collections, optionally filtered."""
        ...

    async def get_collection(
        self,
        collection_id: int,
        *,
        workspace_id: int | None = None,
    ) -> CollectionInfo | None:
        """Get a single collection by ID."""
        ...

    # -- Documents ------------------------------------------------------------

    async def get_documents(
        self,
        collection_id: int,
        *,
        workspace_id: int | None = None,
    ) -> list[DocumentInfo]:
        """List documents in a collection."""
        ...

    async def sync_documents(
        self,
        collection_id: int,
        base_dir: str,
    ) -> SyncResult:
        """Re-index documents from disk into the collection."""
        ...

    # -- FAQ ------------------------------------------------------------------

    async def find_faq_answer(self, question: str) -> str | None:
        """BM25-match a user question against FAQ entries."""
        ...

    async def get_faq_entries(
        self,
        *,
        workspace_id: int | None = None,
    ) -> list[FAQEntryInfo]:
        """List all FAQ entries."""
        ...
