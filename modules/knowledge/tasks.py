"""Knowledge domain background tasks: Wiki RAG embeddings and collection indexes."""

import asyncio
import logging
from pathlib import Path


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
            # Run sync load_collection in a thread to avoid blocking the event loop
            await asyncio.to_thread(wiki_rag.load_collection, col["id"], filenames, base_dir)
            loaded += 1
    if loaded:
        logger.info(f"📚 Wiki RAG: загружено {loaded} коллекционных индексов")
