"""LLM domain startup: provider auto-creation, bridge auto-start."""

import logging
import os
from typing import Optional


logger = logging.getLogger(__name__)


async def get_or_create_default_gemini_provider() -> Optional[dict]:
    """Find existing default Gemini provider or auto-create from GEMINI_API_KEY env.

    Returns provider config dict or None if no API key available.
    """
    from db.integration import async_cloud_provider_manager

    # Try to find existing Gemini provider
    providers = await async_cloud_provider_manager.list_providers(enabled_only=False)
    for p in providers:
        if p.get("provider_type") == "gemini":
            return await async_cloud_provider_manager.get_provider_with_key(p["id"])

    # No Gemini provider exists — create one from env
    api_key = os.getenv("GEMINI_API_KEY", "")
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    if not api_key:
        logger.warning("GEMINI_API_KEY not set, cannot auto-create Gemini cloud provider")
        return None

    logger.info("Auto-creating default Gemini cloud provider from GEMINI_API_KEY...")
    provider = await async_cloud_provider_manager.create_provider(
        name="Gemini (Auto-created)",
        provider_type="gemini",
        api_key=api_key,
        model_name=model_name,
        enabled=True,
        is_default=True,
        description="Auto-created from GEMINI_API_KEY environment variable",
    )
    logger.info(f"Created Gemini provider: {provider['id']}")
    return await async_cloud_provider_manager.get_provider_with_key(provider["id"])


async def auto_start_bridge() -> None:
    """Auto-start CLI-OpenAI Bridge if any enabled claude_bridge provider exists."""
    from bridge_manager import bridge_manager
    from db.integration import async_cloud_provider_manager

    try:
        bridge_providers = await async_cloud_provider_manager.get_by_type(
            "claude_bridge", enabled_only=True
        )
        if not bridge_providers:
            return

        if bridge_manager.is_running:
            logger.info("🌉 Bridge already running, skipping auto-start")
            return

        logger.info("🌉 Auto-starting CLI-OpenAI Bridge (enabled claude_bridge provider found)...")
        result = await bridge_manager.start()
        if result.get("status") == "ok":
            logger.info(f"🌉 Bridge auto-started on port {result.get('port', 8787)}")
        else:
            logger.warning(f"🌉 Bridge auto-start failed: {result.get('error', 'unknown')}")
    except Exception as e:
        logger.error(f"🌉 Error during bridge auto-start: {e}")
