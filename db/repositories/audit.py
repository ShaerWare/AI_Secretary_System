"""
Audit repository for system audit trail.
"""

import json
from datetime import datetime, timedelta
from typing import List

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuditLog
from db.repositories.base import BaseRepository


class AuditRepository(BaseRepository[AuditLog]):
    """Repository for system audit trail."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, AuditLog)

    async def log(
        self,
        action: str,
        resource: str,
        resource_id: str = None,
        user_id: str = None,
        user_ip: str = None,
        details: dict = None,
    ) -> AuditLog:
        """Log an audit event."""
        entry = AuditLog(
            timestamp=datetime.utcnow(),
            action=action,
            resource=resource,
            resource_id=resource_id,
            user_id=user_id,
            user_ip=user_ip,
            details=json.dumps(details, ensure_ascii=False) if details else None,
        )

        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)

        return entry

    async def get_logs(
        self,
        action: str = None,
        resource: str = None,
        user_id: str = None,
        from_date: datetime = None,
        to_date: datetime = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        """Get audit logs with filters."""
        query = select(AuditLog)

        conditions = []
        if action:
            conditions.append(AuditLog.action == action)
        if resource:
            conditions.append(AuditLog.resource == resource)
        if user_id:
            conditions.append(AuditLog.user_id == user_id)
        if from_date:
            conditions.append(AuditLog.timestamp >= from_date)
        if to_date:
            conditions.append(AuditLog.timestamp <= to_date)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(AuditLog.timestamp.desc()).limit(limit).offset(offset)

        result = await self.session.execute(query)
        logs = result.scalars().all()
        return [log.to_dict() for log in logs]

    async def get_recent(self, hours: int = 24, limit: int = 100) -> List[dict]:
        """Get recent audit logs."""
        from_date = datetime.utcnow() - timedelta(hours=hours)
        return await self.get_logs(from_date=from_date, limit=limit)

    async def cleanup_old_logs(self, days: int = 90) -> int:
        """Delete logs older than specified days. Returns count of deleted logs."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = await self.session.execute(delete(AuditLog).where(AuditLog.timestamp < cutoff))
        await self.session.commit()
        return result.rowcount

    async def get_stats(self) -> dict:
        """Get audit log statistics."""
        from sqlalchemy import func

        total = await self.count()

        # Count by action
        result = await self.session.execute(
            select(AuditLog.action, func.count()).group_by(AuditLog.action)
        )
        by_action = dict(result.all())

        # Count by resource
        result = await self.session.execute(
            select(AuditLog.resource, func.count()).group_by(AuditLog.resource)
        )
        by_resource = dict(result.all())

        # Count last 24 hours
        from_date = datetime.utcnow() - timedelta(hours=24)
        result = await self.session.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.timestamp >= from_date)
        )
        last_24h = result.scalar() or 0

        return {
            "total": total,
            "last_24h": last_24h,
            "by_action": by_action,
            "by_resource": by_resource,
        }

    async def export_logs(
        self,
        from_date: datetime = None,
        to_date: datetime = None,
    ) -> List[dict]:
        """Export all logs for the given date range."""
        return await self.get_logs(
            from_date=from_date,
            to_date=to_date,
            limit=100000,  # Large limit for export
        )
