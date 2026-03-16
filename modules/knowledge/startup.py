"""Knowledge domain startup: FAQ reload + Wiki RAG init."""

import logging
from functools import partial


logger = logging.getLogger(__name__)


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

    except Exception as wiki_err:
        logger.warning(f"⚠️ Wiki RAG service not available: {wiki_err}")
