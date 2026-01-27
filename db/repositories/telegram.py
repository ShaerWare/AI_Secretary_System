"""
Telegram repository for managing Telegram user sessions (per bot instance).
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import TelegramSession
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


class TelegramRepository(BaseRepository[TelegramSession]):
    """Repository for Telegram user sessions (supports multi-bot)."""

    def __init__(self, session: AsyncSession, bot_id: str = "default"):
        super().__init__(session, TelegramSession)
        self.bot_id = bot_id

    async def get_session(self, user_id: int, bot_id: str = None) -> Optional[str]:
        """Get chat session ID for Telegram user in specific bot."""
        bot_id = bot_id or self.bot_id
        session = await self.session.get(TelegramSession, (bot_id, user_id))
        return session.chat_session_id if session else None

    async def set_session(
        self,
        user_id: int,
        chat_session_id: str,
        username: str = None,
        first_name: str = None,
        last_name: str = None,
        bot_id: str = None,
    ) -> TelegramSession:
        """Create or update Telegram user session for specific bot."""
        bot_id = bot_id or self.bot_id
        telegram_session = await self.session.get(TelegramSession, (bot_id, user_id))

        if telegram_session:
            telegram_session.chat_session_id = chat_session_id
            telegram_session.username = username
            telegram_session.first_name = first_name
            telegram_session.last_name = last_name
            telegram_session.updated = datetime.utcnow()
        else:
            telegram_session = TelegramSession(
                bot_id=bot_id,
                user_id=user_id,
                chat_session_id=chat_session_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                created=datetime.utcnow(),
                updated=datetime.utcnow(),
            )
            self.session.add(telegram_session)

        await self.session.commit()
        return telegram_session

    async def delete_session(self, user_id: int, bot_id: str = None) -> bool:
        """Delete Telegram user session for specific bot."""
        bot_id = bot_id or self.bot_id
        result = await self.session.execute(
            delete(TelegramSession).where(
                and_(TelegramSession.bot_id == bot_id, TelegramSession.user_id == user_id)
            )
        )
        await self.session.commit()
        return result.rowcount > 0

    async def get_all_sessions(self, bot_id: str = None) -> List[dict]:
        """Get all Telegram sessions for specific bot."""
        query = select(TelegramSession).order_by(TelegramSession.updated.desc())
        if bot_id:
            query = query.where(TelegramSession.bot_id == bot_id)

        result = await self.session.execute(query)
        sessions = result.scalars().all()
        return [s.to_dict() for s in sessions]

    async def get_sessions_for_bot(self, bot_id: str) -> List[dict]:
        """Get all sessions for a specific bot instance."""
        result = await self.session.execute(
            select(TelegramSession)
            .where(TelegramSession.bot_id == bot_id)
            .order_by(TelegramSession.updated.desc())
        )
        sessions = result.scalars().all()
        return [s.to_dict() for s in sessions]

    async def clear_all_sessions(self, bot_id: str = None) -> int:
        """Clear all Telegram sessions (optionally for specific bot)."""
        if bot_id:
            result = await self.session.execute(
                delete(TelegramSession).where(TelegramSession.bot_id == bot_id)
            )
        else:
            result = await self.session.execute(delete(TelegramSession))

        await self.session.commit()
        return result.rowcount

    async def clear_sessions_for_bot(self, bot_id: str) -> int:
        """Clear all sessions for a specific bot instance."""
        return await self.clear_all_sessions(bot_id=bot_id)

    async def get_sessions_as_dict(self, bot_id: str = None) -> Dict[int, str]:
        """Get sessions as user_id -> chat_session_id dict (legacy format)."""
        query = select(TelegramSession)
        if bot_id:
            query = query.where(TelegramSession.bot_id == bot_id)

        result = await self.session.execute(query)
        sessions = result.scalars().all()
        return {s.user_id: s.chat_session_id for s in sessions}

    async def import_from_dict(self, sessions: Dict[int, str], bot_id: str = "default") -> int:
        """
        Import sessions from legacy dict format for specific bot.
        Returns number of imported sessions.
        """
        count = 0
        for user_id, chat_session_id in sessions.items():
            existing = await self.session.get(TelegramSession, (bot_id, user_id))
            if existing:
                continue

            session = TelegramSession(
                bot_id=bot_id,
                user_id=user_id,
                chat_session_id=chat_session_id,
                created=datetime.utcnow(),
                updated=datetime.utcnow(),
            )
            self.session.add(session)
            count += 1

        await self.session.commit()
        return count

    async def migrate_sessions_to_bot(self, bot_id: str = "default") -> int:
        """
        Migrate existing sessions without bot_id to a specific bot.
        This is for backward compatibility during migration.
        """
        # This is handled by the DB schema default value now
        # But we can use this to explicitly set bot_id for old records
        result = await self.session.execute(
            select(TelegramSession).where(TelegramSession.bot_id == "")
        )
        sessions = result.scalars().all()

        count = 0
        for session in sessions:
            session.bot_id = bot_id
            count += 1

        if count > 0:
            await self.session.commit()
            logger.info(f"Migrated {count} sessions to bot_id={bot_id}")

        return count

    async def get_session_count(self, bot_id: str = None) -> int:
        """Get total number of Telegram sessions (optionally for specific bot)."""
        if bot_id:
            from sqlalchemy import func

            result = await self.session.execute(
                select(func.count())
                .select_from(TelegramSession)
                .where(TelegramSession.bot_id == bot_id)
            )
            return result.scalar() or 0
        return await self.count()

    async def get_session_count_by_bot(self) -> Dict[str, int]:
        """Get session counts grouped by bot_id."""
        from sqlalchemy import func

        result = await self.session.execute(
            select(TelegramSession.bot_id, func.count()).group_by(TelegramSession.bot_id)
        )
        return {row[0]: row[1] for row in result.all()}
