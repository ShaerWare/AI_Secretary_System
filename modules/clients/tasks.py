"""Client cards background task: fold quiet dialogues into the clients' cards.

Every 10 minutes — a dialogue counts as finished after ``idle_minutes`` (30 by
default) of silence, so a card is at most ~40 minutes behind the conversation.
"""

import logging


logger = logging.getLogger(__name__)

INTERVAL = 10 * 60


async def client_cards_tick() -> None:
    from app.dependencies import get_container
    from modules.clients.service import client_memory_service

    stats = await client_memory_service.refresh_due(get_container().llm_service)
    if stats["updated"] or stats["failed"]:
        logger.info("Client cards: %s", stats)
