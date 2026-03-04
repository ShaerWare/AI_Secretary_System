"""Telephony services."""

import logging
from datetime import datetime
from typing import List, Optional

from db.database import AsyncSessionLocal
from db.repositories import GSMCallLogRepository, GSMSMSLogRepository


logger = logging.getLogger(__name__)


class GSMService:
    """Async wrapper for GSM call and SMS log repositories."""

    async def create_call(
        self,
        direction: str,
        state: str,
        caller_number: str,
        call_id: Optional[str] = None,
    ) -> dict:
        """Create a new call log entry."""
        async with AsyncSessionLocal() as session:
            repo = GSMCallLogRepository(session)
            call = await repo.create_call(direction, state, caller_number, call_id)
            await session.commit()
            return call.to_dict()

    async def update_call_state(
        self,
        call_id: str,
        state: str,
        answered_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
    ) -> Optional[dict]:
        """Update call state."""
        async with AsyncSessionLocal() as session:
            repo = GSMCallLogRepository(session)
            call = await repo.update_call_state(call_id, state, answered_at, ended_at)
            await session.commit()
            return call.to_dict() if call else None

    async def get_recent_calls(
        self,
        limit: int = 50,
        offset: int = 0,
        state: Optional[str] = None,
    ) -> List[dict]:
        """Get recent calls."""
        async with AsyncSessionLocal() as session:
            repo = GSMCallLogRepository(session)
            calls = await repo.get_recent_calls(limit, offset, state)
            return [c.to_dict() for c in calls]

    async def count_calls(self, state: Optional[str] = None) -> int:
        """Count calls."""
        async with AsyncSessionLocal() as session:
            repo = GSMCallLogRepository(session)
            return await repo.count_calls(state)

    async def create_sms(
        self,
        direction: str,
        number: str,
        text: str,
        status: str,
    ) -> dict:
        """Create SMS log entry."""
        async with AsyncSessionLocal() as session:
            repo = GSMSMSLogRepository(session)
            sms = await repo.create_sms(direction, number, text, status)
            await session.commit()
            return sms.to_dict()

    async def get_recent_sms(self, limit: int = 50, offset: int = 0) -> List[dict]:
        """Get recent SMS messages."""
        async with AsyncSessionLocal() as session:
            repo = GSMSMSLogRepository(session)
            messages = await repo.get_recent_sms(limit, offset)
            return [m.to_dict() for m in messages]

    async def count_sms(self) -> int:
        """Count SMS messages."""
        async with AsyncSessionLocal() as session:
            repo = GSMSMSLogRepository(session)
            return await repo.count_sms()


# Singleton
gsm_service = GSMService()
