"""
GSM repositories for call logs and SMS logs.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import GSMCallLog, GSMSMSLog
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


class GSMCallLogRepository(BaseRepository[GSMCallLog]):
    """Repository for GSM call logs."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, GSMCallLog)

    async def create_call(
        self,
        direction: str,
        state: str,
        caller_number: str,
        call_id: Optional[str] = None,
    ) -> GSMCallLog:
        """Create a new call log entry."""
        call = GSMCallLog(
            id=call_id or str(uuid.uuid4()),
            direction=direction,
            state=state,
            caller_number=caller_number,
            started_at=datetime.utcnow(),
        )
        return await self.create(call)

    async def update_call_state(
        self,
        call_id: str,
        state: str,
        answered_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
    ) -> Optional[GSMCallLog]:
        """Update call state and timestamps."""
        call = await self.get_by_id(call_id)
        if not call:
            return None

        call.state = state
        if answered_at:
            call.answered_at = answered_at
        if ended_at:
            call.ended_at = ended_at
            if call.answered_at:
                call.duration_seconds = int((ended_at - call.answered_at).total_seconds())

        await self.session.commit()
        return call

    async def get_recent_calls(
        self,
        limit: int = 50,
        offset: int = 0,
        state: Optional[str] = None,
    ) -> List[GSMCallLog]:
        """Get recent call logs with optional state filter."""
        query = select(GSMCallLog).order_by(desc(GSMCallLog.started_at))

        if state:
            query = query.where(GSMCallLog.state == state)

        query = query.limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_calls(self, state: Optional[str] = None) -> int:
        """Count calls, optionally filtered by state."""
        query = select(func.count()).select_from(GSMCallLog)
        if state:
            query = query.where(GSMCallLog.state == state)
        result = await self.session.execute(query)
        return result.scalar() or 0


class GSMSMSLogRepository(BaseRepository[GSMSMSLog]):
    """Repository for GSM SMS logs."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, GSMSMSLog)

    async def create_sms(
        self,
        direction: str,
        number: str,
        text: str,
        status: str,
    ) -> GSMSMSLog:
        """Create a new SMS log entry."""
        sms = GSMSMSLog(
            direction=direction,
            number=number,
            text=text,
            status=status,
            sent_at=datetime.utcnow(),
        )
        return await self.create(sms)

    async def get_recent_sms(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> List[GSMSMSLog]:
        """Get recent SMS messages."""
        result = await self.session.execute(
            select(GSMSMSLog).order_by(desc(GSMSMSLog.sent_at)).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def count_sms(self) -> int:
        """Count all SMS messages."""
        result = await self.session.execute(select(func.count()).select_from(GSMSMSLog))
        return result.scalar() or 0
