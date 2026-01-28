# app/routers/audit.py
"""Audit log router - view, export, cleanup audit logs."""

import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from db.database import AsyncSessionLocal
from db.repositories import AuditRepository


router = APIRouter(prefix="/admin/audit", tags=["audit"])


@router.get("/logs")
async def admin_get_audit_logs(
    action: Optional[str] = None,
    resource: Optional[str] = None,
    user_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """Get audit logs with optional filters."""
    # Parse dates if provided
    from_dt = None
    to_dt = None
    if from_date:
        try:
            from_dt = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
        except ValueError:
            pass
    if to_date:
        try:
            to_dt = datetime.fromisoformat(to_date.replace("Z", "+00:00"))
        except ValueError:
            pass

    async with AsyncSessionLocal() as session:
        repo = AuditRepository(session)
        logs = await repo.get_logs(
            action=action,
            resource=resource,
            user_id=user_id,
            from_date=from_dt,
            to_date=to_dt,
            limit=limit,
            offset=offset,
        )
        return {"logs": logs, "count": len(logs)}


@router.get("/stats")
async def admin_get_audit_stats():
    """Get audit log statistics."""
    async with AsyncSessionLocal() as session:
        repo = AuditRepository(session)
        stats = await repo.get_stats()
        return {"stats": stats}


@router.get("/export")
async def admin_export_audit_logs(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    format: str = "json",  # json or csv
):
    """Export audit logs as JSON or CSV."""
    # Parse dates
    from_dt = None
    to_dt = None
    if from_date:
        try:
            from_dt = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
        except ValueError:
            pass
    if to_date:
        try:
            to_dt = datetime.fromisoformat(to_date.replace("Z", "+00:00"))
        except ValueError:
            pass

    async with AsyncSessionLocal() as session:
        repo = AuditRepository(session)
        logs = await repo.export_logs(from_date=from_dt, to_date=to_dt)

    if format == "csv":
        # Convert to CSV
        output = io.StringIO()
        if logs:
            writer = csv.DictWriter(output, fieldnames=logs[0].keys())
            writer.writeheader()
            writer.writerows(logs)
        csv_content = output.getvalue()
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
        )
    else:
        # Return as JSON
        return {"logs": logs, "count": len(logs)}


@router.post("/cleanup")
async def admin_cleanup_audit_logs(days: int = 90):
    """Delete audit logs older than specified days."""
    if days < 7:
        raise HTTPException(status_code=400, detail="Minimum retention period is 7 days")

    async with AsyncSessionLocal() as session:
        repo = AuditRepository(session)
        deleted = await repo.cleanup_old_logs(days=days)
        return {"status": "ok", "deleted": deleted, "retention_days": days}
