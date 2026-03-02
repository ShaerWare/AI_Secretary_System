"""
Bot agent prompt repository for managing LLM prompts per bot/context.
"""

import logging
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BotAgentPrompt
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


class BotAgentPromptRepository(BaseRepository[BotAgentPrompt]):
    """Repository for bot agent prompts."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, BotAgentPrompt)

    async def list_by_bot(self, bot_id: str) -> List[dict]:
        """List all prompts for a bot, ordered by order field."""
        result = await self.session.execute(
            select(BotAgentPrompt)
            .where(BotAgentPrompt.bot_id == bot_id)
            .order_by(BotAgentPrompt.order)
        )
        return [p.to_dict() for p in result.scalars().all()]

    async def get_by_key(self, bot_id: str, prompt_key: str) -> Optional[BotAgentPrompt]:
        """Get a specific prompt by bot_id and prompt_key."""
        result = await self.session.execute(
            select(BotAgentPrompt).where(
                BotAgentPrompt.bot_id == bot_id, BotAgentPrompt.prompt_key == prompt_key
            )
        )
        return result.scalar_one_or_none()

    async def create_prompt(self, bot_id: str, **kwargs: Any) -> dict:
        """Create a new agent prompt."""
        prompt = BotAgentPrompt(bot_id=bot_id, **kwargs)
        self.session.add(prompt)
        await self.session.flush()
        logger.info(f"Created agent prompt: bot_id={bot_id}, key={kwargs.get('prompt_key')}")
        return prompt.to_dict()

    async def update_prompt(self, prompt_id: int, **kwargs: Any) -> Optional[dict]:
        """Update an existing agent prompt."""
        prompt = await self.session.get(BotAgentPrompt, prompt_id)
        if not prompt:
            return None
        for k, v in kwargs.items():
            if hasattr(prompt, k):
                setattr(prompt, k, v)
        prompt.updated = datetime.utcnow()
        await self.session.flush()
        logger.info(f"Updated agent prompt: id={prompt_id}")
        return prompt.to_dict()

    async def delete_prompt(self, prompt_id: int) -> bool:
        """Delete an agent prompt by ID."""
        return await self.delete_by_id(prompt_id)

    async def delete_by_bot(self, bot_id: str) -> int:
        """Delete all prompts for a bot. Returns number of deleted rows."""
        result = await self.session.execute(
            delete(BotAgentPrompt).where(BotAgentPrompt.bot_id == bot_id)
        )
        await self.session.flush()
        deleted: int = result.rowcount  # type: ignore[attr-defined]
        logger.info(f"Deleted {deleted} agent prompts for bot_id={bot_id}")
        return deleted
