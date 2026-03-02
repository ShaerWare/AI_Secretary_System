"""
Bot hardware spec repository for managing GPU model capabilities.
"""

import logging
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BotHardwareSpec
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


class BotHardwareRepository(BaseRepository[BotHardwareSpec]):
    """Repository for bot hardware specifications (GPU audit)."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, BotHardwareSpec)

    async def list_by_bot(self, bot_id: str) -> List[dict]:
        """List all hardware specs for a bot, ordered by order field."""
        result = await self.session.execute(
            select(BotHardwareSpec)
            .where(BotHardwareSpec.bot_id == bot_id)
            .order_by(BotHardwareSpec.order)
        )
        return [h.to_dict() for h in result.scalars().all()]

    async def find_by_gpu(self, bot_id: str, search_text: str) -> List[dict]:
        """Find hardware specs matching a GPU name (case-insensitive LIKE match).

        Args:
            bot_id: Bot instance ID.
            search_text: GPU name search text (e.g., "3060", "RTX", "4090").

        Returns:
            List of matching hardware spec dicts.
        """
        pattern = f"%{search_text}%"
        result = await self.session.execute(
            select(BotHardwareSpec)
            .where(
                BotHardwareSpec.bot_id == bot_id,
                BotHardwareSpec.enabled == True,
                BotHardwareSpec.gpu_name.ilike(pattern),
            )
            .order_by(BotHardwareSpec.order)
        )
        return [h.to_dict() for h in result.scalars().all()]

    async def create_spec(self, bot_id: str, **kwargs: Any) -> dict:
        """Create a new hardware spec entry."""
        spec = BotHardwareSpec(bot_id=bot_id, **kwargs)
        self.session.add(spec)
        await self.session.flush()
        logger.info(f"Created hardware spec: bot_id={bot_id}, gpu={kwargs.get('gpu_name')}")
        return spec.to_dict()

    async def update_spec(self, spec_id: int, **kwargs: Any) -> Optional[dict]:
        """Update an existing hardware spec."""
        spec = await self.session.get(BotHardwareSpec, spec_id)
        if not spec:
            return None
        for k, v in kwargs.items():
            if hasattr(spec, k):
                setattr(spec, k, v)
        await self.session.flush()
        logger.info(f"Updated hardware spec: id={spec_id}")
        return spec.to_dict()

    async def delete_spec(self, spec_id: int) -> bool:
        """Delete a hardware spec by ID."""
        return await self.delete_by_id(spec_id)
