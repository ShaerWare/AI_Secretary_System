"""
Bot follow-up repository for managing follow-up rules and message queue.
"""

import logging
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BotFollowupQueue, BotFollowupRule
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


class BotFollowupRuleRepository(BaseRepository[BotFollowupRule]):
    """Repository for bot follow-up rules."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, BotFollowupRule)

    async def list_rules_by_bot(self, bot_id: str) -> List[dict]:
        """List all follow-up rules for a bot, ordered by order field."""
        result = await self.session.execute(
            select(BotFollowupRule)
            .where(BotFollowupRule.bot_id == bot_id)
            .order_by(BotFollowupRule.order)
        )
        return [r.to_dict() for r in result.scalars().all()]

    async def create_rule(self, bot_id: str, **kwargs: Any) -> dict:
        """Create a new follow-up rule."""
        buttons = kwargs.pop("buttons", None)
        rule = BotFollowupRule(bot_id=bot_id, **kwargs)
        if buttons is not None:
            rule.set_buttons(buttons)
        self.session.add(rule)
        await self.session.flush()
        await self.session.commit()
        logger.info(f"Created follow-up rule: bot_id={bot_id}, name={kwargs.get('name')}")
        return rule.to_dict()

    async def update_rule(self, rule_id: int, **kwargs: Any) -> Optional[dict]:
        """Update an existing follow-up rule."""
        rule = await self.session.get(BotFollowupRule, rule_id)
        if not rule:
            return None
        buttons = kwargs.pop("buttons", None)
        if buttons is not None:
            rule.set_buttons(buttons)
        for k, v in kwargs.items():
            if hasattr(rule, k):
                setattr(rule, k, v)
        rule.updated = datetime.utcnow()
        await self.session.commit()
        logger.info(f"Updated follow-up rule: id={rule_id}")
        return rule.to_dict()

    async def delete_rule(self, rule_id: int) -> bool:
        """Delete a follow-up rule by ID."""
        return await self.delete_by_id(rule_id)


class BotFollowupQueueRepository(BaseRepository[BotFollowupQueue]):
    """Repository for bot follow-up message queue."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, BotFollowupQueue)

    async def enqueue(
        self, bot_id: str, user_id: int, rule_id: int, scheduled_at: datetime
    ) -> dict:
        """Add a follow-up message to the queue.

        Args:
            bot_id: Bot instance ID.
            user_id: Target user ID.
            rule_id: Follow-up rule ID.
            scheduled_at: When the message should be sent.

        Returns:
            Queue entry dict.
        """
        entry = BotFollowupQueue(
            bot_id=bot_id,
            user_id=user_id,
            rule_id=rule_id,
            scheduled_at=scheduled_at,
            status="pending",
            created=datetime.utcnow(),
        )
        self.session.add(entry)
        await self.session.flush()
        await self.session.commit()
        logger.info(
            f"Enqueued follow-up: bot_id={bot_id}, user_id={user_id}, "
            f"rule_id={rule_id}, scheduled_at={scheduled_at}"
        )
        return entry.to_dict()

    async def get_pending(self, before_time: datetime) -> List[dict]:
        """Get all pending follow-up messages scheduled before the given time.

        Args:
            before_time: Get entries scheduled at or before this time.

        Returns:
            List of pending queue entry dicts.
        """
        result = await self.session.execute(
            select(BotFollowupQueue)
            .where(
                BotFollowupQueue.status == "pending",
                BotFollowupQueue.scheduled_at <= before_time,
            )
            .order_by(BotFollowupQueue.scheduled_at.asc())
        )
        return [e.to_dict() for e in result.scalars().all()]

    async def mark_sent(self, entry_id: int) -> Optional[dict]:
        """Mark a queue entry as sent."""
        entry = await self.session.get(BotFollowupQueue, entry_id)
        if not entry:
            return None
        entry.status = "sent"
        entry.sent_at = datetime.utcnow()
        entry.send_count += 1
        await self.session.commit()
        logger.info(f"Marked follow-up as sent: id={entry_id}")
        return entry.to_dict()

    async def mark_cancelled(self, entry_id: int) -> Optional[dict]:
        """Mark a queue entry as cancelled."""
        entry = await self.session.get(BotFollowupQueue, entry_id)
        if not entry:
            return None
        entry.status = "cancelled"
        await self.session.commit()
        logger.info(f"Marked follow-up as cancelled: id={entry_id}")
        return entry.to_dict()

    async def get_queue_by_bot(self, bot_id: str, status: Optional[str] = None) -> List[dict]:
        """Get follow-up queue entries for a bot.

        Args:
            bot_id: Bot instance ID.
            status: Filter by status (optional). E.g., "pending", "sent", "cancelled".

        Returns:
            List of queue entry dicts.
        """
        query = select(BotFollowupQueue).where(BotFollowupQueue.bot_id == bot_id)
        if status is not None:
            query = query.where(BotFollowupQueue.status == status)
        query = query.order_by(BotFollowupQueue.scheduled_at.desc())

        result = await self.session.execute(query)
        return [e.to_dict() for e in result.scalars().all()]
