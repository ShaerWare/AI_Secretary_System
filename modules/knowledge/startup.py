"""Knowledge domain startup: FAQ reload, Wiki RAG init, event subscriptions."""

import logging
import os
from functools import partial
from pathlib import Path


logger = logging.getLogger(__name__)


async def setup_knowledge_event_subscriptions(event_bus) -> None:
    """Register knowledge-domain event handlers."""
    from modules.core.events import DatasetSynced

    async def on_dataset_synced(event: DatasetSynced) -> None:
        """Sync knowledge DB records and RAG index after dataset files are written."""
        from modules.knowledge.service import knowledge_collection_service, knowledge_doc_service

        if event.action == "synced":
            await _handle_dataset_sync(event, knowledge_collection_service, knowledge_doc_service)
        elif event.action == "cleared":
            await _handle_dataset_clear(event, knowledge_collection_service, knowledge_doc_service)
        else:
            logger.warning("DatasetSynced: unknown action=%s", event.action)

    event_bus.subscribe(DatasetSynced, on_dataset_synced)
    logger.info("Knowledge event subscriptions registered (DatasetSynced)")


async def _handle_dataset_sync(event, collection_svc, doc_svc) -> None:
    """Create/update knowledge collection and document records, reload RAG."""
    collection = await collection_svc.get_by_slug(event.collection_slug)
    if not collection:
        collection = await collection_svc.create(
            name=event.collection_name,
            slug=event.collection_slug,
            description=event.collection_description,
            enabled=True,
            base_dir=event.base_dir,
        )
    collection_id = collection["id"]

    # Remove old document records
    existing_docs = await doc_svc.get_by_collection(collection_id)
    for doc in existing_docs:
        await doc_svc.delete(doc["id"])

    # Create new document records
    for doc_info in event.documents:
        await doc_svc.create(
            filename=doc_info["filename"],
            title=doc_info["title"],
            source_type=doc_info["source_type"],
            file_size_bytes=doc_info.get("file_size_bytes", 0),
            section_count=doc_info.get("section_count", 0),
            collection_id=collection_id,
        )

    # Reload RAG index
    from app.dependencies import get_container

    container = get_container()
    wiki_rag = container.wiki_rag_service
    if wiki_rag:
        filenames = [d["filename"] for d in event.documents]
        wiki_rag.reload_collection(collection_id, filenames, Path(event.base_dir))

    # Sync to Vector Search if available
    vs_client = container.vector_search_client
    if vs_client and wiki_rag:
        try:
            from modules.knowledge.tasks import sync_collection_to_vector_search

            await sync_collection_to_vector_search(
                wiki_rag, vs_client, collection_id, event.collection_slug
            )
        except Exception as vs_err:
            logger.warning("Vector Search sync failed for %s: %s", event.collection_slug, vs_err)

    logger.info(
        "DatasetSynced handled: source=%s slug=%s docs=%d",
        event.source,
        event.collection_slug,
        len(event.documents),
    )


async def _handle_dataset_clear(event, collection_svc, doc_svc) -> None:
    """Remove knowledge document records and unload RAG index."""
    collection = await collection_svc.get_by_slug(event.collection_slug)
    if not collection:
        return

    collection_id = collection["id"]

    # Delete document records
    docs = await doc_svc.get_by_collection(collection_id)
    for doc in docs:
        await doc_svc.delete(doc["id"])

    # Unload/clear RAG index
    from app.dependencies import get_container

    container = get_container()
    wiki_rag = container.wiki_rag_service
    if wiki_rag:
        if event.delete_collection:
            wiki_rag.unload_collection(collection_id)
        else:
            wiki_rag.reload_collection(collection_id, [], Path(event.base_dir))

    # Clean up Vector Search
    vs_client = container.vector_search_client
    if vs_client and event.delete_collection:
        try:
            await vs_client.delete_group(event.collection_slug)
        except Exception as vs_err:
            logger.warning(
                "Vector Search group delete failed for %s: %s", event.collection_slug, vs_err
            )

    # Delete collection record if requested
    if event.delete_collection:
        await collection_svc.delete(collection_id)

    logger.info(
        "DatasetSynced(cleared) handled: source=%s slug=%s delete_collection=%s",
        event.source,
        event.collection_slug,
        event.delete_collection,
    )


async def reload_llm_faq(container) -> None:
    """Load FAQ from DB and update LLM service."""
    from db.integration import async_faq_manager

    llm_service = container.llm_service
    if llm_service and hasattr(llm_service, "reload_faq"):
        faq_dict = await async_faq_manager.get_all()
        llm_service.reload_faq(faq_dict)


async def init_wiki_rag(container, deployment_mode: str, task_registry) -> None:
    """Initialize Wiki RAG service with tiered embedding provider."""
    from pathlib import Path

    from modules.knowledge import facade as _facade_module
    from modules.knowledge.facade import KnowledgeServiceImpl

    facade = KnowledgeServiceImpl(container)
    container.knowledge_service = facade
    _facade_module.knowledge_service = facade

    try:
        from app.services.wiki_rag_service import WikiRAGService

        wiki_rag = WikiRAGService(Path("wiki-pages"))
        container.wiki_rag_service = wiki_rag

        # Initialize embedding provider (tiered: local > cloud > none)
        embedding_provider = None

        # Local embeddings (best quality, DEPLOYMENT_MODE=full only)
        if deployment_mode != "cloud":
            try:
                from app.services.embedding_provider import (
                    LOCAL_EMBEDDINGS_AVAILABLE,
                    LocalEmbeddingProvider,
                )

                if LOCAL_EMBEDDINGS_AVAILABLE:
                    embedding_provider = LocalEmbeddingProvider()
                    logger.info("✅ Wiki RAG: local embeddings (sentence-transformers)")
            except Exception as local_err:
                logger.debug(f"Wiki RAG: local embeddings not available: {local_err}")

        # Cloud embeddings from active LLM provider
        llm_service = container.llm_service
        if not embedding_provider and llm_service and hasattr(llm_service, "config"):
            try:
                cloud_config = llm_service.config
                provider_type = cloud_config.get("provider_type", "")
                api_key = cloud_config.get("api_key", "")

                if provider_type == "gemini" and api_key:
                    from app.services.embedding_provider import GeminiEmbeddingProvider

                    embedding_provider = GeminiEmbeddingProvider(api_key=api_key)
                    logger.info("✅ Wiki RAG: cloud embeddings (Gemini)")
                elif api_key and cloud_config.get("base_url"):
                    from app.services.embedding_provider import OpenAIEmbeddingProvider

                    embedding_provider = OpenAIEmbeddingProvider(
                        api_key=api_key,
                        base_url=cloud_config["base_url"],
                    )
                    logger.info("✅ Wiki RAG: cloud embeddings (OpenAI-compatible)")
            except Exception as cloud_err:
                logger.debug(f"Wiki RAG: cloud embeddings not available: {cloud_err}")

        if embedding_provider:
            wiki_rag.set_embedding_provider(embedding_provider)
            from modules.knowledge.tasks import build_wiki_embeddings

            task_registry.register("wiki-embeddings", partial(build_wiki_embeddings, wiki_rag))
        else:
            logger.info("📚 Wiki RAG: BM25 only (no embedding provider)")

        # Load per-collection indexes in background
        from modules.knowledge.tasks import load_collection_indexes

        task_registry.register(
            "wiki-collection-indexes", partial(load_collection_indexes, wiki_rag)
        )

        # Initialize Vector Search client if configured
        vector_url = os.environ.get("VECTOR_SEARCH_URL", "")
        vector_token = os.environ.get("VECTOR_SEARCH_TOKEN", "")
        if vector_url:
            try:
                from app.services.vector_search_client import VectorSearchClient
                from modules.knowledge.tasks import sync_vector_search

                vs_client = VectorSearchClient(base_url=vector_url, token=vector_token)
                container.vector_search_client = vs_client
                wiki_rag.set_vector_search_client(vs_client)

                task_registry.register(
                    "vector-search-sync", partial(sync_vector_search, wiki_rag, vs_client)
                )
                logger.info("✅ Vector Search client: %s", vector_url)
            except Exception as vs_err:
                logger.warning("⚠️ Vector Search client init failed: %s", vs_err)

    except Exception as wiki_err:
        logger.warning(f"⚠️ Wiki RAG service not available: {wiki_err}")
