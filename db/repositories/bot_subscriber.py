"""
Bot subscriber repository for managing news/updates subscriptions.
"""

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BotSubscriber
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


class BotSubscriberRepository(BaseRepository[BotSubscriber]):
    """Repository for bot news/updates subscribers."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, BotSubscriber)

    async def subscribe(
        self,
        bot_id: str,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> dict:
        """Subscribe a user to bot updates. If already exists, re-subscribe and update profile.

        Args:
            bot_id: Bot instance ID.
            user_id: Telegram user ID.
            username: Telegram username (without @).
            first_name: Telegram first name.

        Returns:
            Subscriber dict.
        """
        result = await self.session.execute(
            select(BotSubscriber).where(
                BotSubscriber.bot_id == bot_id, BotSubscriber.user_id == user_id
            )
        )
        subscriber = result.scalar_one_or_none()

        if subscriber:
            # Re-subscribe if previously unsubscribed, and update profile
            subscriber.subscribed = True
            subscriber.unsubscribed_at = None
            subscriber.subscribed_at = datetime.utcnow()
            if username is not None:
                subscriber.username = username
            if first_name is not None:
                subscriber.first_name = first_name
            await self.session.flush()
            logger.info(f"Re-subscribed user: bot_id={bot_id}, user_id={user_id}")
            return subscriber.to_dict()

        # Create new subscription
        subscriber = BotSubscriber(
            bot_id=bot_id,
            user_id=user_id,
            username=username,
            first_name=first_name,
            subscribed=True,
            subscribed_at=datetime.utcnow(),
        )
        self.session.add(subscriber)
        await self.session.flush()
        logger.info(f"Subscribed user: bot_id={bot_id}, user_id={user_id}")
        return subscriber.to_dict()

    async def unsubscribe(self, bot_id: str, user_id: int) -> Optional[dict]:
        """Unsubscribe a user from bot updates.

        Args:
            bot_id: Bot instance ID.
            user_id: Telegram user ID.

        Returns:
            Updated subscriber dict, or None if not found.
        """
        result = await self.session.execute(
            select(BotSubscriber).where(
                BotSubscriber.bot_id == bot_id, BotSubscriber.user_id == user_id
            )
        )
        subscriber = result.scalar_one_or_none()
        if not subscriber:
            return None

        subscriber.subscribed = False
        subscriber.unsubscribed_at = datetime.utcnow()
        await self.session.flush()
        logger.info(f"Unsubscribed user: bot_id={bot_id}, user_id={user_id}")
        return subscriber.to_dict()

    async def is_subscribed(self, bot_id: str, user_id: int) -> bool:
        """Check if a user is actively subscribed.

        Args:
            bot_id: Bot instance ID.
            user_id: Telegram user ID.

        Returns:
            True if user is subscribed, False otherwise.
        """
        result = await self.session.execute(
            select(BotSubscriber).where(
                BotSubscriber.bot_id == bot_id,
                BotSubscriber.user_id == user_id,
                BotSubscriber.subscribed == True,
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_active_subscribers(self, bot_id: str) -> List[int]:
        """Get list of active subscriber user IDs for broadcasting.

        Args:
            bot_id: Bot instance ID.

        Returns:
            List of user IDs.
        """
        result = await self.session.execute(
            select(BotSubscriber.user_id).where(
                BotSubscriber.bot_id == bot_id,
                BotSubscriber.subscribed == True,
            )
        )
        return [row[0] for row in result.all()]

    async def count_subscribers(self, bot_id: str) -> int:
        """Count active subscribers for a bot.

        Args:
            bot_id: Bot instance ID.

        Returns:
            Number of active subscribers.
        """
        result = await self.session.execute(
            select(func.count(BotSubscriber.id)).where(
                BotSubscriber.bot_id == bot_id,
                BotSubscriber.subscribed == True,
            )
        )
        count: int = result.scalar() or 0
        return count

    async def list_by_bot(self, bot_id: str) -> List[dict]:
        """List all subscribers (active and inactive) for a bot.

        Args:
            bot_id: Bot instance ID.

        Returns:
            List of subscriber dicts.
        """
        result = await self.session.execute(
            select(BotSubscriber)
            .where(BotSubscriber.bot_id == bot_id)
            .order_by(BotSubscriber.subscribed_at.desc())
        )
        return [s.to_dict() for s in result.scalars().all()]
