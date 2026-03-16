"""Knowledge domain startup: FAQ reload."""

import logging


logger = logging.getLogger(__name__)


async def reload_llm_faq(container) -> None:
    """Load FAQ from DB and update LLM service."""
    from db.integration import async_faq_manager

    llm_service = container.llm_service
    if llm_service and hasattr(llm_service, "reload_faq"):
        faq_dict = await async_faq_manager.get_all()
        llm_service.reload_faq(faq_dict)
