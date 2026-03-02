"""
Bot user profile repository for managing user FSM state, segment, quiz answers.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BotUserProfile
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


class BotUserProfileRepository(BaseRepository[BotUserProfile]):
    """Repository for bot user profiles."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, BotUserProfile)

    async def get_or_create(
        self,
        bot_id: str,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> dict:
        """Get existing user profile or create a new one.

        Args:
            bot_id: Bot instance ID.
            user_id: Telegram user ID.
            username: Telegram username (optional).
            first_name: User's first name (optional).

        Returns:
            User profile dict.
        """
        result = await self.session.execute(
            select(BotUserProfile).where(
                BotUserProfile.bot_id == bot_id, BotUserProfile.user_id == user_id
            )
        )
        profile = result.scalar_one_or_none()

        if profile:
            # Update last activity and user info if changed
            profile.last_activity = datetime.utcnow()
            if username and profile.username != username:
                profile.username = username
            if first_name and profile.first_name != first_name:
                profile.first_name = first_name
            await self.session.flush()
            return profile.to_dict()

        # Create new profile
        profile = BotUserProfile(
            bot_id=bot_id,
            user_id=user_id,
            username=username,
            first_name=first_name,
            state="new",
            last_activity=datetime.utcnow(),
            created=datetime.utcnow(),
            updated=datetime.utcnow(),
        )
        self.session.add(profile)
        await self.session.flush()
        logger.info(f"Created user profile: bot_id={bot_id}, user_id={user_id}")
        return profile.to_dict()

    async def update_state(self, bot_id: str, user_id: int, state: str) -> Optional[dict]:
        """Update user FSM state."""
        result = await self.session.execute(
            select(BotUserProfile).where(
                BotUserProfile.bot_id == bot_id, BotUserProfile.user_id == user_id
            )
        )
        profile = result.scalar_one_or_none()
        if not profile:
            return None
        profile.state = state
        profile.last_activity = datetime.utcnow()
        profile.updated = datetime.utcnow()
        await self.session.flush()
        logger.debug(f"Updated state to '{state}': bot_id={bot_id}, user_id={user_id}")
        return profile.to_dict()

    async def update_segment(
        self, bot_id: str, user_id: int, segment: str, path: Optional[str] = None
    ) -> Optional[dict]:
        """Update user segment and path."""
        result = await self.session.execute(
            select(BotUserProfile).where(
                BotUserProfile.bot_id == bot_id, BotUserProfile.user_id == user_id
            )
        )
        profile = result.scalar_one_or_none()
        if not profile:
            return None
        profile.segment = segment
        if path is not None:
            profile.path = path
        profile.updated = datetime.utcnow()
        await self.session.flush()
        logger.info(f"Updated segment to '{segment}': bot_id={bot_id}, user_id={user_id}")
        return profile.to_dict()

    async def set_quiz_answers(self, bot_id: str, user_id: int, answers: dict) -> Optional[dict]:
        """Set quiz answers for a user profile."""
        result = await self.session.execute(
            select(BotUserProfile).where(
                BotUserProfile.bot_id == bot_id, BotUserProfile.user_id == user_id
            )
        )
        profile = result.scalar_one_or_none()
        if not profile:
            return None
        profile.set_quiz_answers(answers)
        profile.updated = datetime.utcnow()
        await self.session.flush()
        return profile.to_dict()

    async def set_discovery_data(self, bot_id: str, user_id: int, data: dict) -> Optional[dict]:
        """Set discovery flow data for a user profile."""
        result = await self.session.execute(
            select(BotUserProfile).where(
                BotUserProfile.bot_id == bot_id, BotUserProfile.user_id == user_id
            )
        )
        profile = result.scalar_one_or_none()
        if not profile:
            return None
        profile.set_discovery_data(data)
        profile.updated = datetime.utcnow()
        await self.session.flush()
        return profile.to_dict()

    async def set_followup_optout(
        self, bot_id: str, user_id: int, optout: bool = True
    ) -> Optional[dict]:
        """Set follow-up opt-out status for a user."""
        result = await self.session.execute(
            select(BotUserProfile).where(
                BotUserProfile.bot_id == bot_id, BotUserProfile.user_id == user_id
            )
        )
        profile = result.scalar_one_or_none()
        if not profile:
            return None
        profile.followup_optout = optout
        profile.updated = datetime.utcnow()
        await self.session.flush()
        logger.info(f"Set followup_optout={optout}: bot_id={bot_id}, user_id={user_id}")
        return profile.to_dict()

    async def list_by_bot(
        self,
        bot_id: str,
        segment: Optional[str] = None,
        state: Optional[str] = None,
    ) -> List[dict]:
        """List user profiles for a bot with optional segment/state filters.

        Args:
            bot_id: Bot instance ID.
            segment: Filter by segment key (optional).
            state: Filter by FSM state (optional).

        Returns:
            List of user profile dicts.
        """
        query = select(BotUserProfile).where(BotUserProfile.bot_id == bot_id)
        if segment is not None:
            query = query.where(BotUserProfile.segment == segment)
        if state is not None:
            query = query.where(BotUserProfile.state == state)
        query = query.order_by(BotUserProfile.last_activity.desc())

        result = await self.session.execute(query)
        return [p.to_dict() for p in result.scalars().all()]

    async def get_inactive_users(self, bot_id: str, hours: int) -> List[dict]:
        """Get users who have been inactive for at least the specified hours.

        Args:
            bot_id: Bot instance ID.
            hours: Minimum inactivity period in hours.

        Returns:
            List of inactive user profile dicts.
        """
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        result = await self.session.execute(
            select(BotUserProfile)
            .where(
                BotUserProfile.bot_id == bot_id,
                BotUserProfile.last_activity < cutoff,
                BotUserProfile.followup_optout == False,
            )
            .order_by(BotUserProfile.last_activity.asc())
        )
        return [p.to_dict() for p in result.scalars().all()]

    async def delete_by_bot_user(self, bot_id: str, user_id: int) -> bool:
        """Delete a user profile by bot_id and user_id."""
        result = await self.session.execute(
            select(BotUserProfile).where(
                BotUserProfile.bot_id == bot_id, BotUserProfile.user_id == user_id
            )
        )
        profile = result.scalar_one_or_none()
        if not profile:
            return False
        await self.session.delete(profile)
        await self.session.flush()
        logger.info(f"Deleted user profile: bot_id={bot_id}, user_id={user_id}")
        return True

    async def count_by_segment(self, bot_id: str) -> Dict[str, int]:
        """Count users per segment for a bot.

        Returns:
            Dict mapping segment_key to user count. Unsegmented users are under "none".
        """
        result = await self.session.execute(
            select(BotUserProfile.segment, func.count(BotUserProfile.id))
            .where(BotUserProfile.bot_id == bot_id)
            .group_by(BotUserProfile.segment)
        )
        counts: Dict[str, int] = {}
        for segment_key, cnt in result.all():
            counts[segment_key or "none"] = cnt
        return counts
