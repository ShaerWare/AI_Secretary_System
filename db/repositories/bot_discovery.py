"""
Bot discovery response repository for managing custom path discovery flow answers.
"""

import logging
from datetime import datetime
from typing import List

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BotDiscoveryResponse
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


class BotDiscoveryRepository(BaseRepository[BotDiscoveryResponse]):
    """Repository for bot discovery flow responses."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, BotDiscoveryResponse)

    async def save_response(
        self,
        bot_id: str,
        user_id: int,
        step: int,
        question: str,
        answer: str,
    ) -> dict:
        """Save a discovery flow response.

        Args:
            bot_id: Bot instance ID.
            user_id: User who answered.
            step: Step number (1-5).
            question: The question that was asked.
            answer: User's answer (free text or selected value).

        Returns:
            Created response dict.
        """
        response = BotDiscoveryResponse(
            bot_id=bot_id,
            user_id=user_id,
            step=step,
            question=question,
            answer=answer,
            created=datetime.utcnow(),
        )
        self.session.add(response)
        await self.session.flush()
        logger.debug(f"Saved discovery response: bot_id={bot_id}, user_id={user_id}, step={step}")
        return response.to_dict()

    async def get_responses(self, bot_id: str, user_id: int) -> List[dict]:
        """Get all discovery responses for a specific user.

        Args:
            bot_id: Bot instance ID.
            user_id: User ID.

        Returns:
            List of response dicts ordered by step.
        """
        result = await self.session.execute(
            select(BotDiscoveryResponse)
            .where(
                BotDiscoveryResponse.bot_id == bot_id,
                BotDiscoveryResponse.user_id == user_id,
            )
            .order_by(BotDiscoveryResponse.step)
        )
        return [r.to_dict() for r in result.scalars().all()]

    async def clear_responses(self, bot_id: str, user_id: int) -> int:
        """Clear all discovery responses for a specific user.

        Args:
            bot_id: Bot instance ID.
            user_id: User ID.

        Returns:
            Number of deleted rows.
        """
        result = await self.session.execute(
            delete(BotDiscoveryResponse).where(
                BotDiscoveryResponse.bot_id == bot_id,
                BotDiscoveryResponse.user_id == user_id,
            )
        )
        await self.session.flush()
        deleted: int = result.rowcount  # type: ignore[attr-defined]
        logger.info(f"Cleared {deleted} discovery responses: bot_id={bot_id}, user_id={user_id}")
        return deleted

    async def list_all_by_bot(self, bot_id: str) -> List[dict]:
        """List all discovery responses for a bot (all users).

        Args:
            bot_id: Bot instance ID.

        Returns:
            List of response dicts ordered by user_id, then step.
        """
        result = await self.session.execute(
            select(BotDiscoveryResponse)
            .where(BotDiscoveryResponse.bot_id == bot_id)
            .order_by(BotDiscoveryResponse.user_id, BotDiscoveryResponse.step)
        )
        return [r.to_dict() for r in result.scalars().all()]
