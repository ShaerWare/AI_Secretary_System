"""
TTS Preset repository for managing voice presets.
"""

import json
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import TTSPreset
from db.redis_client import CacheKey, cache_delete, cache_get, cache_set
from db.repositories.base import BaseRepository


class PresetRepository(BaseRepository[TTSPreset]):
    """Repository for TTS voice presets."""

    CACHE_TTL = 600  # 10 minutes

    def __init__(self, session: AsyncSession):
        super().__init__(session, TTSPreset)

    def _cache_key(self, name: Optional[str] = None) -> str:
        if name:
            return f"{CacheKey.TTS_PRESET}:{name}"
        return f"{CacheKey.TTS_PRESET}:all"

    async def _invalidate_cache(self) -> None:
        """Invalidate all preset caches."""
        await cache_delete(self._cache_key())

    async def get_all_presets(
        self,
        include_builtin: bool = True,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> Dict[str, dict]:
        """
        Get all presets as name->params dict, filtered by owner and workspace.
        Uses Redis cache when no owner/workspace filter.
        """
        # Try cache first (only when no owner/workspace filter)
        if owner_id is None and workspace_id is None:
            cached: Optional[Dict[str, dict]] = await cache_get(self._cache_key())
            if cached:
                if not include_builtin:
                    return {k: v for k, v in cached.items() if not v.get("builtin", False)}
                return cached

        # Fetch from database
        query = select(TTSPreset)
        if owner_id is not None:
            query = query.where((TTSPreset.owner_id == owner_id) | (TTSPreset.owner_id.is_(None)))
        query = self._apply_workspace_filter(query, workspace_id)
        result = await self.session.execute(query)
        presets = result.scalars().all()

        preset_dict = {}
        for p in presets:
            preset_dict[p.name] = {
                **p.get_params(),
                "builtin": p.builtin,
            }

        # Cache for 10 minutes (only when no owner/workspace filter)
        if owner_id is None and workspace_id is None:
            await cache_set(self._cache_key(), preset_dict, self.CACHE_TTL)

        if not include_builtin:
            return {k: v for k, v in preset_dict.items() if not v.get("builtin", False)}
        return preset_dict

    async def get_custom_presets(
        self, owner_id: Optional[int] = None, workspace_id: Optional[int] = None
    ) -> Dict[str, dict]:
        """Get only custom (non-builtin) presets."""
        return await self.get_all_presets(
            include_builtin=False, owner_id=owner_id, workspace_id=workspace_id
        )

    async def get_by_name(self, name: str) -> Optional[dict]:
        """Get preset by name."""
        result = await self.session.execute(select(TTSPreset).where(TTSPreset.name == name))
        preset = result.scalar_one_or_none()
        return preset.to_dict() if preset else None

    async def create_preset(
        self,
        name: str,
        params: dict,
        builtin: bool = False,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> dict:
        """Create new preset."""
        create_kwargs: dict[str, Any] = {}
        if workspace_id is not None:
            create_kwargs["workspace_id"] = workspace_id

        preset = TTSPreset(
            name=name,
            params=json.dumps(params, ensure_ascii=False),
            builtin=builtin,
            owner_id=owner_id,
            created=datetime.utcnow(),
            updated=datetime.utcnow(),
            **create_kwargs,
        )

        self.session.add(preset)
        await self.session.commit()
        await self.session.refresh(preset)
        await self._invalidate_cache()

        return preset.to_dict()

    async def update_preset(
        self,
        name: str,
        params: dict,
        workspace_id: Optional[int] = None,
    ) -> Optional[dict]:
        """Update existing preset parameters, with optional workspace check."""
        query = select(TTSPreset).where(TTSPreset.name == name)
        if workspace_id is not None and hasattr(TTSPreset, "workspace_id"):
            query = query.where(TTSPreset.workspace_id == workspace_id)
        result = await self.session.execute(query)
        preset = result.scalar_one_or_none()

        if not preset:
            return None

        preset.params = json.dumps(params, ensure_ascii=False)
        preset.updated = datetime.utcnow()

        await self.session.commit()
        await self._invalidate_cache()

        data: dict[str, Any] = preset.to_dict()
        return data

    async def delete_preset(self, name: str, workspace_id: Optional[int] = None) -> bool:
        """Delete preset by name, with optional workspace check."""
        query = (
            delete(TTSPreset)
            .where(TTSPreset.name == name)
            .where(TTSPreset.builtin == False)  # Can't delete builtin
        )
        if workspace_id is not None and hasattr(TTSPreset, "workspace_id"):
            query = query.where(TTSPreset.workspace_id == workspace_id)
        result = await self.session.execute(query)
        await self.session.commit()
        await self._invalidate_cache()
        return bool(result.rowcount > 0)  # type: ignore[attr-defined]

    async def import_from_dict(self, presets: Dict[str, dict]) -> int:
        """
        Import presets from dict format.
        Returns number of imported presets.
        """
        count = 0
        for name, params in presets.items():
            existing = await self.get_by_name(name)
            if existing:
                continue

            preset = TTSPreset(
                name=name,
                params=json.dumps(params, ensure_ascii=False),
                builtin=False,
                created=datetime.utcnow(),
                updated=datetime.utcnow(),
            )
            self.session.add(preset)
            count += 1

        await self.session.commit()
        await self._invalidate_cache()
        return count

    async def export_to_dict(self) -> Dict[str, dict]:
        """Export custom presets to dict format."""
        return await self.get_custom_presets()

    async def get_preset_count(self) -> dict:
        """Get preset counts."""
        from sqlalchemy import func

        total = await self.count()

        result = await self.session.execute(
            select(func.count()).select_from(TTSPreset).where(TTSPreset.builtin == True)
        )
        builtin = result.scalar() or 0

        return {
            "total": total,
            "builtin": builtin,
            "custom": total - builtin,
        }
