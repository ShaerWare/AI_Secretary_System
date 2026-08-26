"""LLM Router for WhatsApp bot.

Reuses the same LLMRouter class from telegram_bot — routes requests
to the orchestrator chat API via HTTP. This module provides a
WhatsApp-specific singleton that reads config from WhatsApp bot state.
"""

import logging
from typing import Optional

from telegram_bot.services.llm_router import LLMRouter


logger = logging.getLogger(__name__)

_router: Optional[LLMRouter] = None


def get_llm_router(
    orchestrator_url: Optional[str] = None,
    claude_provider_id: Optional[str] = None,
) -> LLMRouter:
    """Get or create the singleton LLM router for WhatsApp bot.

    Reuses the same LLMRouter class but with WhatsApp-specific config.
    """
    global _router
    if _router is None:
        import os

        from ..state import get_bot_config

        url = orchestrator_url or os.environ.get("ORCHESTRATOR_URL", "http://localhost:8002")
        provider_id = claude_provider_id or os.environ.get("CLAUDE_PROVIDER_ID", "claude-bridge")

        default_backend = "vllm"
        bot_config = get_bot_config()
        if bot_config and bot_config.llm_backend:
            default_backend = bot_config.llm_backend
            logger.info(f"WhatsApp LLM Router: using bot config backend: {default_backend}")

        # Tag sessions as WhatsApp. The orchestrator resolves a session's RAG
        # collections by matching source/source_id against the channel instance,
        # so reporting the Telegram default left this bot's catalog binding
        # unread and silently fell through to "every enabled collection".
        _router = LLMRouter(
            orchestrator_url=url,
            claude_provider_id=provider_id,
            default_backend=default_backend,
            source="whatsapp",
            instance_id=bot_config.instance_id if bot_config else None,
        )
    return _router
