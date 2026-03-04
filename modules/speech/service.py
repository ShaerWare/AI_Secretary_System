"""Speech services."""

import logging
from typing import Dict, Optional

from db.database import AsyncSessionLocal
from db.repositories import PresetRepository


logger = logging.getLogger(__name__)


class PresetService:
    """Async TTS preset manager using database."""

    async def get_all(
        self, owner_id: Optional[int] = None, workspace_id: Optional[int] = None
    ) -> Dict[str, dict]:
        """Get all presets."""
        async with AsyncSessionLocal() as session:
            repo = PresetRepository(session)
            return await repo.get_all_presets(owner_id=owner_id, workspace_id=workspace_id)

    async def get_custom(
        self, owner_id: Optional[int] = None, workspace_id: Optional[int] = None
    ) -> Dict[str, dict]:
        """Get only custom presets."""
        async with AsyncSessionLocal() as session:
            repo = PresetRepository(session)
            return await repo.get_custom_presets(owner_id=owner_id, workspace_id=workspace_id)

    async def create(
        self,
        name: str,
        params: dict,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> dict:
        """Create new preset."""
        async with AsyncSessionLocal() as session:
            repo = PresetRepository(session)
            result = await repo.create_preset(
                name, params, owner_id=owner_id, workspace_id=workspace_id
            )
            await session.commit()
            return result

    async def update(
        self, name: str, params: dict, workspace_id: Optional[int] = None
    ) -> Optional[dict]:
        """Update preset."""
        async with AsyncSessionLocal() as session:
            repo = PresetRepository(session)
            result = await repo.update_preset(name, params, workspace_id=workspace_id)
            await session.commit()
            return result

    async def delete(self, name: str, workspace_id: Optional[int] = None) -> bool:
        """Delete preset."""
        async with AsyncSessionLocal() as session:
            repo = PresetRepository(session)
            result = await repo.delete_preset(name, workspace_id=workspace_id)
            await session.commit()
            return result


# Singleton
preset_service = PresetService()
