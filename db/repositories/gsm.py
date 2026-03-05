"""
GSM repositories for call logs and SMS logs.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import asc, desc, func, literal, select, union_all
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

        await self.session.flush()
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

    async def get_calls_by_number(
        self,
        number: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[GSMCallLog]:
        """Get calls for a specific phone number."""
        result = await self.session.execute(
            select(GSMCallLog)
            .where(GSMCallLog.caller_number == number)
            .order_by(asc(GSMCallLog.started_at))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())


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

    async def get_conversations(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> List[dict]:
        """Get SMS conversations grouped by phone number."""
        # Subquery: aggregate SMS by number
        sms_sub = (
            select(
                GSMSMSLog.number,
                func.max(GSMSMSLog.sent_at).label("last_time"),
                func.count().label("message_count"),
            )
            .group_by(GSMSMSLog.number)
            .subquery()
        )

        # Subquery: count calls per number
        calls_sub = (
            select(
                GSMCallLog.caller_number.label("number"),
                func.count().label("call_count"),
            )
            .group_by(GSMCallLog.caller_number)
            .subquery()
        )

        # Get all unique numbers from both SMS and calls
        sms_numbers = select(GSMSMSLog.number.label("number")).distinct()
        call_numbers = select(GSMCallLog.caller_number.label("number")).distinct()
        all_numbers = union_all(sms_numbers, call_numbers).subquery()
        unique_numbers = select(all_numbers.c.number).distinct().subquery()

        # Join with aggregates
        query = (
            select(
                unique_numbers.c.number,
                func.coalesce(sms_sub.c.last_time, None).label("last_time"),
                func.coalesce(sms_sub.c.message_count, literal(0)).label("message_count"),
                func.coalesce(calls_sub.c.call_count, literal(0)).label("call_count"),
            )
            .outerjoin(sms_sub, unique_numbers.c.number == sms_sub.c.number)
            .outerjoin(calls_sub, unique_numbers.c.number == calls_sub.c.number)
            .order_by(desc("last_time"))
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(query)
        rows = result.all()

        conversations = []
        for row in rows:
            # Fetch last message text
            last_msg_q = (
                select(GSMSMSLog.text, GSMSMSLog.direction)
                .where(GSMSMSLog.number == row.number)
                .order_by(desc(GSMSMSLog.sent_at))
                .limit(1)
            )
            last_msg_result = await self.session.execute(last_msg_q)
            last_msg = last_msg_result.first()

            conversations.append(
                {
                    "number": row.number,
                    "last_message": last_msg.text if last_msg else "",
                    "last_direction": last_msg.direction if last_msg else "",
                    "last_time": row.last_time.isoformat() if row.last_time else None,
                    "message_count": row.message_count,
                    "call_count": row.call_count,
                }
            )

        return conversations

    async def get_messages_by_number(
        self,
        number: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[GSMSMSLog]:
        """Get SMS messages for a specific phone number (chronological)."""
        result = await self.session.execute(
            select(GSMSMSLog)
            .where(GSMSMSLog.number == number)
            .order_by(asc(GSMSMSLog.sent_at))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_conversations(self) -> int:
        """Count unique phone numbers across SMS and calls."""
        sms_numbers = select(GSMSMSLog.number.label("number")).distinct()
        call_numbers = select(GSMCallLog.caller_number.label("number")).distinct()
        all_numbers = union_all(sms_numbers, call_numbers).subquery()
        query = select(func.count(func.distinct(all_numbers.c.number)))
        result = await self.session.execute(query)
        return result.scalar() or 0
