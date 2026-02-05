"""Usage tracking repository for TTS/STT/LLM services."""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import UsageLimits, UsageLog
from db.repositories.base import BaseRepository


class UsageRepository(BaseRepository[UsageLog]):
    """Repository for usage tracking and analytics."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, UsageLog)

    async def log_usage(
        self,
        service_type: str,
        action: str,
        units_consumed: int = 1,
        source: Optional[str] = None,
        source_id: Optional[str] = None,
        cost_usd: Optional[float] = None,
        details: Optional[dict] = None,
    ) -> dict:
        """Log a service usage event."""
        entry = UsageLog(
            timestamp=datetime.utcnow(),
            service_type=service_type,
            action=action,
            source=source,
            source_id=source_id,
            units_consumed=units_consumed,
            cost_usd=cost_usd,
            details=json.dumps(details, ensure_ascii=False) if details else None,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry.to_dict()

    async def get_usage(
        self,
        service_type: Optional[str] = None,
        action: Optional[str] = None,
        source: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        """Get usage logs with filters."""
        query = select(UsageLog)

        conditions = []
        if service_type:
            conditions.append(UsageLog.service_type == service_type)
        if action:
            conditions.append(UsageLog.action == action)
        if source:
            conditions.append(UsageLog.source == source)
        if from_date:
            conditions.append(UsageLog.timestamp >= from_date)
        if to_date:
            conditions.append(UsageLog.timestamp <= to_date)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(UsageLog.timestamp.desc()).limit(limit).offset(offset)

        result = await self.session.execute(query)
        logs = result.scalars().all()
        return [log.to_dict() for log in logs]

    async def get_usage_stats(
        self,
        service_type: Optional[str] = None,
        period_days: int = 30,
    ) -> Dict:
        """Get usage statistics for a period."""
        from_date = datetime.utcnow() - timedelta(days=period_days)

        # Build base condition
        base_condition = UsageLog.timestamp >= from_date
        if service_type:
            base_condition = and_(base_condition, UsageLog.service_type == service_type)

        # Total usage by service
        result = await self.session.execute(
            select(
                UsageLog.service_type,
                func.sum(UsageLog.units_consumed),
                func.count(UsageLog.id),
                func.coalesce(func.sum(UsageLog.cost_usd), 0),
            )
            .where(UsageLog.timestamp >= from_date)
            .group_by(UsageLog.service_type)
        )

        by_service = {}
        for service, total_units, count, total_cost in result.all():
            by_service[service] = {
                "units": int(total_units or 0),
                "requests": int(count),
                "cost_usd": float(total_cost or 0),
            }

        # Usage by source (admin, telegram, widget)
        result = await self.session.execute(
            select(
                UsageLog.source,
                func.sum(UsageLog.units_consumed),
                func.count(UsageLog.id),
            )
            .where(UsageLog.timestamp >= from_date)
            .group_by(UsageLog.source)
        )

        by_source = {}
        for source, total_units, count in result.all():
            by_source[source or "unknown"] = {
                "units": int(total_units or 0),
                "requests": int(count),
            }

        # Daily breakdown for charts (last 7 days)
        daily_breakdown = []
        for i in range(min(7, period_days)):
            day_start = datetime.utcnow().replace(
                hour=0, minute=0, second=0, microsecond=0
            ) - timedelta(days=i)
            day_end = day_start + timedelta(days=1)

            result = await self.session.execute(
                select(
                    func.sum(UsageLog.units_consumed),
                    func.count(UsageLog.id),
                    func.coalesce(func.sum(UsageLog.cost_usd), 0),
                ).where(and_(UsageLog.timestamp >= day_start, UsageLog.timestamp < day_end))
            )
            row = result.one()
            daily_breakdown.append(
                {
                    "date": day_start.strftime("%Y-%m-%d"),
                    "units": int(row[0] or 0),
                    "requests": int(row[1]),
                    "cost_usd": float(row[2] or 0),
                }
            )

        return {
            "period_days": period_days,
            "from_date": from_date.isoformat(),
            "by_service": by_service,
            "by_source": by_source,
            "daily": list(reversed(daily_breakdown)),
        }

    async def get_period_usage(
        self,
        service_type: str,
        period_type: str,  # "daily", "monthly"
    ) -> int:
        """Get total usage for current period (for limit checking)."""
        now = datetime.utcnow()

        if period_type == "daily":
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period_type == "monthly":
            period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            period_start = now - timedelta(days=30)

        result = await self.session.execute(
            select(func.coalesce(func.sum(UsageLog.units_consumed), 0)).where(
                and_(
                    UsageLog.service_type == service_type,
                    UsageLog.timestamp >= period_start,
                )
            )
        )
        return int(result.scalar() or 0)

    async def cleanup_old_logs(self, days: int = 90) -> int:
        """Delete logs older than specified days."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = await self.session.execute(delete(UsageLog).where(UsageLog.timestamp < cutoff))
        await self.session.commit()
        return int(result.rowcount)  # type: ignore[attr-defined]


class UsageLimitsRepository(BaseRepository[UsageLimits]):
    """Repository for usage limits configuration."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, UsageLimits)

    async def get_limit(self, service_type: str, limit_type: str) -> Optional[dict]:
        """Get a specific usage limit."""
        result = await self.session.execute(
            select(UsageLimits).where(
                UsageLimits.service_type == service_type,
                UsageLimits.limit_type == limit_type,
            )
        )
        limit = result.scalars().first()
        return limit.to_dict() if limit else None

    async def get_all_limits(self, enabled_only: bool = True) -> List[dict]:
        """Get all limits."""
        query = select(UsageLimits)
        if enabled_only:
            query = query.where(UsageLimits.enabled.is_(True))
        result = await self.session.execute(query)
        return [limit.to_dict() for limit in result.scalars().all()]

    async def set_limit(
        self,
        service_type: str,
        limit_type: str,
        limit_value: int,
        hard_limit: bool = False,
        warning_threshold: int = 80,
    ) -> dict:
        """Create or update a usage limit."""
        # Check if exists
        result = await self.session.execute(
            select(UsageLimits).where(
                UsageLimits.service_type == service_type,
                UsageLimits.limit_type == limit_type,
            )
        )
        limit = result.scalars().first()

        if limit:
            limit.limit_value = limit_value
            limit.hard_limit = hard_limit
            limit.warning_threshold = warning_threshold
            limit.updated = datetime.utcnow()
        else:
            limit = UsageLimits(
                service_type=service_type,
                limit_type=limit_type,
                limit_value=limit_value,
                hard_limit=hard_limit,
                warning_threshold=warning_threshold,
            )
            self.session.add(limit)

        await self.session.commit()
        await self.session.refresh(limit)
        return limit.to_dict()

    async def delete_limit(self, service_type: str, limit_type: str) -> bool:
        """Delete a usage limit."""
        result = await self.session.execute(
            select(UsageLimits).where(
                UsageLimits.service_type == service_type,
                UsageLimits.limit_type == limit_type,
            )
        )
        limit = result.scalars().first()
        if limit:
            await self.session.delete(limit)
            await self.session.commit()
            return True
        return False

    async def check_limit(
        self,
        service_type: str,
        current_usage: int,
    ) -> Dict:
        """Check if usage is within limits and return status."""
        limits = await self.get_all_limits(enabled_only=True)
        service_limits = [lim for lim in limits if lim["service_type"] == service_type]

        warnings: List[str] = []
        limit_statuses: List[dict] = []
        result: Dict = {
            "within_limits": True,
            "warnings": warnings,
            "blocked": False,
            "limits": limit_statuses,
        }

        for lim in service_limits:
            limit_value = lim["limit_value"]
            warning_threshold = lim.get("warning_threshold", 80)
            usage_percent = (current_usage / limit_value * 100) if limit_value > 0 else 0

            limit_status = {
                "limit_type": lim["limit_type"],
                "limit_value": limit_value,
                "current_usage": current_usage,
                "usage_percent": round(usage_percent, 1),
                "hard_limit": lim["hard_limit"],
            }
            limit_statuses.append(limit_status)

            if usage_percent >= 100:
                if lim["hard_limit"]:
                    result["within_limits"] = False
                    result["blocked"] = True
                    warnings.append(
                        f"{service_type} {lim['limit_type']} лимит превышен ({current_usage}/{limit_value})"
                    )
                else:
                    warnings.append(
                        f"{service_type} {lim['limit_type']} лимит превышен (soft limit)"
                    )
            elif usage_percent >= warning_threshold:
                warnings.append(
                    f"{service_type} {lim['limit_type']} использовано {usage_percent:.0f}%"
                )

        return result
