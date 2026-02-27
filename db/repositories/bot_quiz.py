"""
Bot quiz question repository for managing segmentation quiz questions.
"""

import logging
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BotQuizQuestion
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


class BotQuizRepository(BaseRepository[BotQuizQuestion]):
    """Repository for bot quiz questions."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, BotQuizQuestion)

    async def list_by_bot(self, bot_id: str) -> List[dict]:
        """List all quiz questions for a bot, ordered by order field."""
        result = await self.session.execute(
            select(BotQuizQuestion)
            .where(BotQuizQuestion.bot_id == bot_id)
            .order_by(BotQuizQuestion.order)
        )
        return [q.to_dict() for q in result.scalars().all()]

    async def get_by_key(self, bot_id: str, question_key: str) -> Optional[BotQuizQuestion]:
        """Get a specific quiz question by bot_id and question_key."""
        result = await self.session.execute(
            select(BotQuizQuestion).where(
                BotQuizQuestion.bot_id == bot_id, BotQuizQuestion.question_key == question_key
            )
        )
        return result.scalar_one_or_none()

    async def create_question(self, bot_id: str, **kwargs: Any) -> dict:
        """Create a new quiz question."""
        # Handle options JSON field
        options = kwargs.pop("options", [])
        question = BotQuizQuestion(bot_id=bot_id, **kwargs)
        if options:
            question.set_options(options)
        self.session.add(question)
        await self.session.flush()
        await self.session.commit()
        logger.info(f"Created quiz question: bot_id={bot_id}, key={kwargs.get('question_key')}")
        return question.to_dict()

    async def update_question(self, question_id: int, **kwargs: Any) -> Optional[dict]:
        """Update an existing quiz question."""
        question = await self.session.get(BotQuizQuestion, question_id)
        if not question:
            return None
        # Handle options JSON field
        options = kwargs.pop("options", None)
        if options is not None:
            question.set_options(options)
        for k, v in kwargs.items():
            if hasattr(question, k):
                setattr(question, k, v)
        question.updated = datetime.utcnow()
        await self.session.commit()
        logger.info(f"Updated quiz question: id={question_id}")
        return question.to_dict()

    async def delete_question(self, question_id: int) -> bool:
        """Delete a quiz question by ID."""
        return await self.delete_by_id(question_id)

    async def reorder(self, bot_id: str, question_ids: List[int]) -> bool:
        """Reorder quiz questions by updating their order field.

        Args:
            bot_id: Bot instance ID.
            question_ids: List of question IDs in desired order.

        Returns:
            True if reorder was successful.
        """
        for idx, qid in enumerate(question_ids):
            await self.session.execute(
                update(BotQuizQuestion)
                .where(BotQuizQuestion.id == qid, BotQuizQuestion.bot_id == bot_id)
                .values(order=idx + 1, updated=datetime.utcnow())
            )
        await self.session.commit()
        logger.info(f"Reordered {len(question_ids)} quiz questions for bot_id={bot_id}")
        return True
