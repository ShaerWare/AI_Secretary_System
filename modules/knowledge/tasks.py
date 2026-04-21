"""Knowledge domain background tasks: Wiki RAG embeddings, collection indexes, vector search sync."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from app.services.vector_search_client import VectorSearchClient
    from app.services.wiki_rag_service import WikiRAGService

logger = logging.getLogger(__name__)


async def build_wiki_embeddings(wiki_rag) -> None:
    """Build embedding vectors for Wiki RAG sections."""
    # Run sync build_embeddings in a thread to avoid blocking the event loop
    result = await asyncio.to_thread(wiki_rag.build_embeddings)
    if result.get("status") == "ok":
        total = result.get("total", result.get("cached", 0))
        new = result.get("new", 0)
        logger.info(f"✅ Wiki RAG embeddings: {total} секций ({new} новых)")
    elif result.get("status") == "error":
        logger.warning(f"⚠️ Wiki RAG embeddings error: {result.get('error')}")


async def load_collection_indexes(wiki_rag) -> None:
    """Load per-collection BM25 indexes."""
    from db.integration import async_knowledge_collection_manager

    collections = await async_knowledge_collection_manager.get_all(enabled_only=True)
    loaded = 0
    for col in collections:
        filenames = await async_knowledge_collection_manager.get_document_filenames(col["id"])
        if filenames:
            base_dir = Path(col.get("base_dir", "wiki-pages"))
            slug = col.get("slug") or None
            # Run sync load_collection in a thread to avoid blocking the event loop
            await asyncio.to_thread(
                wiki_rag.load_collection, col["id"], filenames, base_dir, slug
            )
            loaded += 1
    if loaded:
        logger.info(f"📚 Wiki RAG: загружено {loaded} коллекционных индексов")


async def sync_vector_search(wiki_rag: WikiRAGService, vs_client: VectorSearchClient) -> None:
    """Full sync: upsert all sections from all collections into Vector Search."""
    from db.integration import async_knowledge_collection_manager

    # Check connectivity
    health = await vs_client.health()
    if not health:
        logger.warning("Vector Search: service unavailable, skipping sync")
        return

    collections = await async_knowledge_collection_manager.get_all(enabled_only=True)

    # Ensure per-collection BM25 indexes are loaded. The background task
    # registry starts this sync in parallel with `wiki-collection-indexes`,
    # so when sync runs first (or the manual endpoint is called before
    # collections were hot) `_collection_indexes` is empty and each
    # sync_collection_to_vector_search would return 0 — only the global
    # default collection would reach Vector Search. Load whatever is missing.
    missing = [col for col in collections if col["id"] not in wiki_rag._collection_indexes]
    if missing:
        logger.info("Vector Search sync: loading %d missing collection indexes first", len(missing))
        for col in missing:
            filenames = await async_knowledge_collection_manager.get_document_filenames(col["id"])
            if not filenames:
                continue
            base_dir = Path(col.get("base_dir", "wiki-pages"))
            slug = col.get("slug") or None
            await asyncio.to_thread(
                wiki_rag.load_collection, col["id"], filenames, base_dir, slug
            )

    total_upserted = 0

    # Sync per-collection indexes
    for col in collections:
        slug = col.get("slug", str(col["id"]))
        count = await sync_collection_to_vector_search(wiki_rag, vs_client, col["id"], slug)
        total_upserted += count

    # Sync global index (legacy "default" group — kept for back-compat with
    # widgets/bots querying without a collection filter).
    for section in wiki_rag.sections:
        text = f"{section.title}\n{section.body}"
        await vs_client.upsert(
            text=text,
            doc_id=wiki_rag._section_id(section),
            group="default",
            metadata={"title": section.title, "source_file": section.source_file},
        )
        total_upserted += 1

    logger.info("✅ Vector Search sync: %d sections upserted", total_upserted)


async def sync_collection_to_vector_search(
    wiki_rag: WikiRAGService,
    vs_client: VectorSearchClient,
    collection_id: int,
    collection_slug: str,
) -> int:
    """Sync a single collection's sections to Vector Search. Returns upsert count."""
    group = collection_slug or str(collection_id)
    idx = wiki_rag._collection_indexes.get(collection_id)
    if not idx:
        return 0

    count = 0
    for section in idx.sections:
        text = f"{section.title}\n{section.body}"
        # `doc_id` must be unique per section. `source_file` collapsed many
        # sections (e.g. all products in one WooCommerce md file) onto the
        # same doc_id, and vector-search upsert REPLACES chunks under the
        # same doc_id — so only the last section per file survived. Reuse
        # the same hash WikiRAGService uses for its embedding cache.
        await vs_client.upsert(
            text=text,
            doc_id=wiki_rag._section_id(section),
            group=group,
            metadata={"title": section.title, "source_file": section.source_file},
        )
        count += 1

    logger.info(
        "Vector Search: synced %d sections for collection %s (slug=%s)",
        count,
        collection_id,
        group,
    )
    return count
