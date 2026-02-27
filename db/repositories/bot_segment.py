"""
Bot segment repository for managing user segment definitions and routing rules.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BotSegment
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


class BotSegmentRepository(BaseRepository[BotSegment]):
    """Repository for bot user segments."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, BotSegment)

    async def list_by_bot(self, bot_id: str) -> List[dict]:
        """List all segments for a bot, ordered by priority (descending)."""
        result = await self.session.execute(
            select(BotSegment)
            .where(BotSegment.bot_id == bot_id)
            .order_by(BotSegment.priority.desc())
        )
        return [s.to_dict() for s in result.scalars().all()]

    async def get_by_key(self, bot_id: str, segment_key: str) -> Optional[BotSegment]:
        """Get a specific segment by bot_id and segment_key."""
        result = await self.session.execute(
            select(BotSegment).where(
                BotSegment.bot_id == bot_id, BotSegment.segment_key == segment_key
            )
        )
        return result.scalar_one_or_none()

    async def match_segment(self, bot_id: str, quiz_answers: Dict[str, str]) -> Optional[dict]:
        """Match quiz answers against segment rules, returning the highest priority match.

        Args:
            bot_id: Bot instance ID.
            quiz_answers: Dict of question_key -> answer_value from quiz.

        Returns:
            Matched segment dict or None if no match.
        """
        result = await self.session.execute(
            select(BotSegment)
            .where(BotSegment.bot_id == bot_id, BotSegment.enabled == True)
            .order_by(BotSegment.priority.desc())
        )
        segments = result.scalars().all()

        for segment in segments:
            rules = segment.get_match_rules()
            if not rules:
                continue
            # All rules must match
            matched = True
            for key, expected_value in rules.items():
                if quiz_answers.get(key) != expected_value:
                    matched = False
                    break
            if matched:
                logger.debug(
                    f"Matched segment {segment.segment_key} for bot_id={bot_id}, "
                    f"answers={quiz_answers}"
                )
                return segment.to_dict()

        logger.debug(f"No segment matched for bot_id={bot_id}, answers={quiz_answers}")
        return None

    async def create_segment(self, bot_id: str, **kwargs: Any) -> dict:
        """Create a new segment."""
        match_rules = kwargs.pop("match_rules", {})
        segment = BotSegment(bot_id=bot_id, **kwargs)
        if match_rules:
            segment.set_match_rules(match_rules)
        self.session.add(segment)
        await self.session.flush()
        await self.session.commit()
        logger.info(f"Created segment: bot_id={bot_id}, key={kwargs.get('segment_key')}")
        return segment.to_dict()

    async def update_segment(self, segment_id: int, **kwargs: Any) -> Optional[dict]:
        """Update an existing segment."""
        segment = await self.session.get(BotSegment, segment_id)
        if not segment:
            return None
        match_rules = kwargs.pop("match_rules", None)
        if match_rules is not None:
            segment.set_match_rules(match_rules)
        for k, v in kwargs.items():
            if hasattr(segment, k):
                setattr(segment, k, v)
        await self.session.commit()
        logger.info(f"Updated segment: id={segment_id}")
        return segment.to_dict()

    async def delete_segment(self, segment_id: int) -> bool:
        """Delete a segment by ID."""
        return await self.delete_by_id(segment_id)
