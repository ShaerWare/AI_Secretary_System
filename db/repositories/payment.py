"""
Payment log repository for Telegram bot payments.
"""

import logging
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PaymentLog
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


class PaymentRepository(BaseRepository[PaymentLog]):
    """Repository for payment transaction logging."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, PaymentLog)

    async def log_payment(
        self,
        bot_id: str,
        user_id: int,
        username: Optional[str],
        payment_type: str,
        product_id: str,
        amount: int,
        currency: str,
        telegram_payment_id: Optional[str] = None,
        provider_payment_id: Optional[str] = None,
    ) -> dict:
        """Log a completed payment."""
        entry = PaymentLog(
            bot_id=bot_id,
            user_id=user_id,
            username=username,
            payment_type=payment_type,
            product_id=product_id,
            amount=amount,
            currency=currency,
            telegram_payment_id=telegram_payment_id,
            provider_payment_id=provider_payment_id,
            status="completed",
        )
        self.session.add(entry)
        await self.session.flush()
        logger.info(f"Payment logged: bot={bot_id}, user={user_id}, {amount} {currency}")
        return entry.to_dict()

    async def get_payments_for_bot(self, bot_id: str, limit: int = 100) -> List[dict]:
        """Get payment history for a bot instance."""
        result = await self.session.execute(
            select(PaymentLog)
            .where(PaymentLog.bot_id == bot_id)
            .order_by(PaymentLog.created.desc())
            .limit(limit)
        )
        return [p.to_dict() for p in result.scalars().all()]

    async def get_payments_for_user(self, bot_id: str, user_id: int) -> List[dict]:
        """Get payment history for a specific user in a bot."""
        result = await self.session.execute(
            select(PaymentLog)
            .where(PaymentLog.bot_id == bot_id, PaymentLog.user_id == user_id)
            .order_by(PaymentLog.created.desc())
        )
        return [p.to_dict() for p in result.scalars().all()]

    async def get_payment_stats(self, bot_id: str) -> Dict:
        """Get payment statistics for a bot instance."""
        # Total count
        count_result = await self.session.execute(
            select(func.count(PaymentLog.id)).where(PaymentLog.bot_id == bot_id)
        )
        total_count = count_result.scalar() or 0

        # Sum by currency
        sum_result = await self.session.execute(
            select(
                PaymentLog.currency,
                func.sum(PaymentLog.amount),
                func.count(PaymentLog.id),
            )
            .where(PaymentLog.bot_id == bot_id)
            .group_by(PaymentLog.currency)
        )
        by_currency = {}
        for currency, total_amount, count in sum_result.all():
            by_currency[currency] = {
                "count": count,
                "total_amount": total_amount or 0,
            }

        return {
            "total_count": total_count,
            "by_currency": by_currency,
        }
