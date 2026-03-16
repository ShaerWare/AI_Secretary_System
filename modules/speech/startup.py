"""Speech domain startup: voice preset reload."""

import logging

logger = logging.getLogger(__name__)


async def reload_voice_presets(container) -> None:
    """Load TTS presets from DB and update voice services."""
    from db.integration import async_preset_manager

    presets_dict = await async_preset_manager.get_custom()
    for svc in [container.voice_service, container.anna_voice_service]:
        if svc and hasattr(svc, "reload_presets"):
            svc.reload_presets(presets_dict)
