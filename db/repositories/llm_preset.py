"""
Repository for LLM presets (vLLM generation parameters + system prompts).
"""

from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import DEFAULT_LLM_PRESETS, LLMPreset

from .base import BaseRepository


class LLMPresetRepository(BaseRepository[LLMPreset]):
    """Repository for LLM presets CRUD operations"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, LLMPreset)

    async def get_all_enabled(self) -> list[LLMPreset]:
        """Get all enabled presets"""
        result = await self.session.execute(
            select(LLMPreset).where(LLMPreset.enabled == True).order_by(LLMPreset.name)
        )
        return list(result.scalars().all())

    async def get_default(self) -> Optional[LLMPreset]:
        """Get the default preset"""
        result = await self.session.execute(select(LLMPreset).where(LLMPreset.is_default == True))
        preset: Optional[LLMPreset] = result.scalar_one_or_none()
        return preset

    async def set_default(self, preset_id: str) -> bool:
        """Set a preset as default (unset others)"""
        # Unset all defaults
        await self.session.execute(update(LLMPreset).values(is_default=False))
        # Set new default
        preset = await self.get_by_id(preset_id)
        if preset:
            preset.is_default = True
            await self.session.flush()
            return True
        return False

    async def update_params(
        self,
        preset_id: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        repetition_penalty: Optional[float] = None,
    ) -> Optional[LLMPreset]:
        """Update generation parameters for a preset"""
        preset = await self.get_by_id(preset_id)
        if not preset:
            return None

        if temperature is not None:
            preset.temperature = temperature
        if max_tokens is not None:
            preset.max_tokens = max_tokens
        if top_p is not None:
            preset.top_p = top_p
        if repetition_penalty is not None:
            preset.repetition_penalty = repetition_penalty

        await self.session.flush()
        return preset

    async def update_prompt(self, preset_id: str, system_prompt: str) -> Optional[LLMPreset]:
        """Update system prompt for a preset"""
        preset = await self.get_by_id(preset_id)
        if not preset:
            return None

        preset.system_prompt = system_prompt
        await self.session.flush()
        return preset

    async def ensure_defaults(self) -> int:
        """Ensure default presets exist in the database. Returns count of created presets."""
        created = 0
        for preset_data in DEFAULT_LLM_PRESETS:
            existing = await self.get_by_id(preset_data["id"])
            if not existing:
                preset = LLMPreset(**preset_data)
                self.session.add(preset)
                created += 1

        if created > 0:
            await self.session.flush()

        return created
