"""Monitoring services."""

import logging
from typing import Any, Dict, List, Optional

from db.database import AsyncSessionLocal
from db.repositories import AuditRepository, PaymentRepository
from db.retry import retry_on_busy


logger = logging.getLogger(__name__)


class AuditService:
    """Async audit logger using database."""

    @retry_on_busy()
    async def log(
        self,
        action: str,
        resource: str,
        resource_id: Optional[str] = None,
        user_id: Optional[str] = None,
        user_ip: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        """Log audit event."""
        async with AsyncSessionLocal() as session:
            repo = AuditRepository(session)
            await repo.log(action, resource, resource_id, user_id, user_ip, details)
            await session.commit()

    async def get_logs(
        self,
        action: Optional[str] = None,
        resource: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        """Get audit logs."""
        async with AsyncSessionLocal() as session:
            repo = AuditRepository(session)
            return await repo.get_logs(action=action, resource=resource, limit=limit)

    async def get_recent(self, hours: int = 24) -> List[dict]:
        """Get recent logs."""
        async with AsyncSessionLocal() as session:
            repo = AuditRepository(session)
            return await repo.get_recent(hours)


class PaymentService:
    """Async wrapper for PaymentRepository."""

    @retry_on_busy()
    async def log_payment(self, **kwargs: Any) -> dict:
        """Log a completed payment."""
        async with AsyncSessionLocal() as session:
            repo = PaymentRepository(session)
            result = await repo.log_payment(**kwargs)
            await session.commit()
            return result

    async def get_payments_for_bot(self, bot_id: str, limit: int = 100) -> List[dict]:
        """Get payment history for a bot instance."""
        async with AsyncSessionLocal() as session:
            repo = PaymentRepository(session)
            return await repo.get_payments_for_bot(bot_id, limit)

    async def get_payment_stats(self, bot_id: str) -> Dict[str, Any]:
        """Get payment statistics for a bot instance."""
        async with AsyncSessionLocal() as session:
            repo = PaymentRepository(session)
            return await repo.get_payment_stats(bot_id)


# Singletons
audit_service = AuditService()
payment_service = PaymentService()
