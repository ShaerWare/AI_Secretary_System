"""Ideal data shapes for the Knowledge domain.

These TypedDicts describe the *target* API contract, not necessarily
the current ``to_dict()`` output.  As services migrate toward the
Protocol interfaces (``protocols.py``), their return types should
converge to these shapes.
"""

from __future__ import annotations

from typing import TypedDict


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class SearchResult(TypedDict):
    """Single search hit returned by KnowledgeService.search()."""

    title: str
    body: str
    source_file: str
    score: float
    collection_id: int | None


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


class CollectionInfo(TypedDict):
    """Read-only view of a knowledge collection."""

    id: int
    name: str
    slug: str
    description: str | None
    enabled: bool
    base_dir: str
    document_count: int
    created: str | None
    updated: str | None


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


class DocumentInfo(TypedDict):
    """Read-only view of a knowledge document."""

    id: int
    filename: str
    title: str
    source_type: str  # "manual" | "import" | "wiki"
    file_size_bytes: int
    section_count: int
    collection_id: int | None
    created: str | None
    updated: str | None


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


class SyncResult(TypedDict):
    """Result of KnowledgeService.sync_documents()."""

    collection_id: int
    documents_synced: int
    sections_indexed: int


# ---------------------------------------------------------------------------
# FAQ
# ---------------------------------------------------------------------------


class FAQEntryInfo(TypedDict):
    """Read-only view of a FAQ entry."""

    id: int
    question: str
    answer: str
    keywords: list[str]
    enabled: bool
    hit_count: int
    created: str | None
    updated: str | None
