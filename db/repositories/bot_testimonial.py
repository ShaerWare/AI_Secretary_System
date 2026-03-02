"""
Bot testimonial repository for managing social proof testimonials.
"""

import logging
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BotTestimonial
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


class BotTestimonialRepository(BaseRepository[BotTestimonial]):
    """Repository for bot testimonials (social proof)."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, BotTestimonial)

    async def list_by_bot(self, bot_id: str) -> List[dict]:
        """List all testimonials for a bot, ordered by order field."""
        result = await self.session.execute(
            select(BotTestimonial)
            .where(BotTestimonial.bot_id == bot_id)
            .order_by(BotTestimonial.order)
        )
        return [t.to_dict() for t in result.scalars().all()]

    async def get_random(self, bot_id: str) -> Optional[dict]:
        """Get one random enabled testimonial for a bot.

        Returns:
            Random testimonial dict, or None if no enabled testimonials exist.
        """
        result = await self.session.execute(
            select(BotTestimonial)
            .where(BotTestimonial.bot_id == bot_id, BotTestimonial.enabled == True)
            .order_by(func.random())
            .limit(1)
        )
        testimonial = result.scalar_one_or_none()
        return testimonial.to_dict() if testimonial else None

    async def create_testimonial(self, bot_id: str, **kwargs: Any) -> dict:
        """Create a new testimonial."""
        testimonial = BotTestimonial(
            bot_id=bot_id,
            created=datetime.utcnow(),
            **kwargs,
        )
        self.session.add(testimonial)
        await self.session.flush()
        logger.info(f"Created testimonial: bot_id={bot_id}, author={kwargs.get('author')}")
        return testimonial.to_dict()

    async def update_testimonial(self, testimonial_id: int, **kwargs: Any) -> Optional[dict]:
        """Update an existing testimonial."""
        testimonial = await self.session.get(BotTestimonial, testimonial_id)
        if not testimonial:
            return None
        for k, v in kwargs.items():
            if hasattr(testimonial, k):
                setattr(testimonial, k, v)
        await self.session.flush()
        logger.info(f"Updated testimonial: id={testimonial_id}")
        return testimonial.to_dict()

    async def delete_testimonial(self, testimonial_id: int) -> bool:
        """Delete a testimonial by ID."""
        return await self.delete_by_id(testimonial_id)
