"""
Bot event repository for funnel event tracking and analytics.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BotEvent
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


# Funnel stages in order for conversion tracking
FUNNEL_STAGES = [
    "start",
    "quiz_started",
    "quiz_completed",
    "value_shown",
    "cta_clicked",
    "checkout_started",
    "payment_initiated",
    "payment_completed",
    "github_clicked",
    "github_starred",
]


class BotEventRepository(BaseRepository[BotEvent]):
    """Repository for bot funnel events."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, BotEvent)

    async def log_event(
        self,
        bot_id: str,
        user_id: int,
        event_type: str,
        event_data: Optional[dict] = None,
    ) -> dict:
        """Log a funnel event.

        Args:
            bot_id: Bot instance ID.
            user_id: User who triggered the event.
            event_type: Event type (e.g., "start", "quiz_completed", "cta_clicked").
            event_data: Optional JSON-serializable event data.

        Returns:
            Created event dict.
        """
        event = BotEvent(
            bot_id=bot_id,
            user_id=user_id,
            event_type=event_type,
            event_data=json.dumps(event_data, ensure_ascii=False) if event_data else None,
            created=datetime.utcnow(),
        )
        self.session.add(event)
        await self.session.flush()
        logger.debug(f"Logged event: bot_id={bot_id}, user_id={user_id}, type={event_type}")
        return event.to_dict()

    async def get_events_by_bot(
        self,
        bot_id: str,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        event_type: Optional[str] = None,
        limit: int = 1000,
    ) -> List[dict]:
        """Get events for a bot with optional date range and type filter.

        Args:
            bot_id: Bot instance ID.
            date_from: Start of date range (optional).
            date_to: End of date range (optional).
            event_type: Filter by event type (optional).
            limit: Max number of events to return.

        Returns:
            List of event dicts.
        """
        query = select(BotEvent).where(BotEvent.bot_id == bot_id)
        if date_from is not None:
            query = query.where(BotEvent.created >= date_from)
        if date_to is not None:
            query = query.where(BotEvent.created <= date_to)
        if event_type is not None:
            query = query.where(BotEvent.event_type == event_type)
        query = query.order_by(BotEvent.created.desc()).limit(limit)

        result = await self.session.execute(query)
        return [e.to_dict() for e in result.scalars().all()]

    async def count_by_type(self, bot_id: str, event_type: str, days: int = 30) -> int:
        """Count events of a specific type within the last N days.

        Args:
            bot_id: Bot instance ID.
            event_type: Event type to count.
            days: Number of days to look back.

        Returns:
            Event count.
        """
        since = datetime.utcnow() - timedelta(days=days)
        result = await self.session.execute(
            select(func.count(BotEvent.id)).where(
                BotEvent.bot_id == bot_id,
                BotEvent.event_type == event_type,
                BotEvent.created >= since,
            )
        )
        count: int = result.scalar() or 0
        return count

    async def get_funnel(self, bot_id: str, days: int = 30) -> Dict[str, int]:
        """Get funnel stage counts for the last N days.

        Counts unique users (not events) per funnel stage.

        Args:
            bot_id: Bot instance ID.
            days: Number of days to look back.

        Returns:
            Dict mapping funnel stage to unique user count.
        """
        since = datetime.utcnow() - timedelta(days=days)
        funnel: Dict[str, int] = {}

        for stage in FUNNEL_STAGES:
            result = await self.session.execute(
                select(func.count(func.distinct(BotEvent.user_id))).where(
                    BotEvent.bot_id == bot_id,
                    BotEvent.event_type == stage,
                    BotEvent.created >= since,
                )
            )
            funnel[stage] = result.scalar() or 0

        return funnel
