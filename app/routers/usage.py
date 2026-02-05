# app/routers/usage.py
"""Usage tracking router - view, configure, and analyze usage logs."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth_manager import User, get_current_user
from db.database import AsyncSessionLocal
from db.repositories.usage import UsageLimitsRepository, UsageRepository


router = APIRouter(prefix="/admin/usage", tags=["usage"])


# =============================================================================
# Request/Response Models
# =============================================================================


class UsageLogRequest(BaseModel):
    """Request to log a usage event."""

    service_type: str = Field(..., description="Service type: tts, stt, llm")
    action: str = Field(..., description="Action performed: synthesis, transcribe, chat")
    units_consumed: int = Field(1, ge=0, description="Units consumed (chars, tokens, seconds)")
    source: Optional[str] = Field(None, description="Source: admin, telegram, widget")
    source_id: Optional[str] = Field(None, description="Source instance ID")
    cost_usd: Optional[float] = Field(None, ge=0, description="Cost in USD")
    details: Optional[dict] = Field(None, description="Additional details (JSON)")


class UsageLimitRequest(BaseModel):
    """Request to set a usage limit."""

    service_type: str = Field(..., description="Service type: tts, stt, llm")
    limit_type: str = Field(..., description="Limit type: daily, monthly")
    limit_value: int = Field(..., gt=0, description="Limit value in units")
    hard_limit: bool = Field(False, description="Enforce hard limit (block on exceed)")
    warning_threshold: int = Field(80, ge=0, le=100, description="Warning threshold percentage")


# =============================================================================
# Usage Logs Endpoints
# =============================================================================


@router.get("/logs")
async def admin_get_usage_logs(
    service_type: Optional[str] = None,
    action: Optional[str] = None,
    source: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    user: User = Depends(get_current_user),
):
    """Get usage logs with optional filters."""
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
        repo = UsageRepository(session)
        logs = await repo.get_usage(
            service_type=service_type,
            action=action,
            source=source,
            from_date=from_dt,
            to_date=to_dt,
            limit=min(limit, 500),  # Cap at 500
            offset=offset,
        )
        return {"logs": logs, "count": len(logs)}


@router.get("/stats")
async def admin_get_usage_stats(
    service_type: Optional[str] = None,
    period_days: int = 30,
    user: User = Depends(get_current_user),
):
    """Get usage statistics for the specified period."""
    if period_days < 1 or period_days > 365:
        raise HTTPException(status_code=400, detail="Period must be between 1 and 365 days")

    async with AsyncSessionLocal() as session:
        repo = UsageRepository(session)
        stats = await repo.get_usage_stats(
            service_type=service_type,
            period_days=period_days,
        )
        return {"stats": stats}


@router.post("/log")
async def admin_log_usage(request: UsageLogRequest):
    """
    Log a usage event.

    This endpoint is called by services (TTS, STT, LLM) to track usage.
    No authentication required for internal service calls.
    """
    if request.service_type not in ("tts", "stt", "llm"):
        raise HTTPException(status_code=400, detail="Invalid service_type. Must be: tts, stt, llm")

    async with AsyncSessionLocal() as session:
        repo = UsageRepository(session)
        log = await repo.log_usage(
            service_type=request.service_type,
            action=request.action,
            units_consumed=request.units_consumed,
            source=request.source,
            source_id=request.source_id,
            cost_usd=request.cost_usd,
            details=request.details,
        )
        return {"log": log}


@router.post("/cleanup")
async def admin_cleanup_usage_logs(
    days: int = 90,
    user: User = Depends(get_current_user),
):
    """Delete usage logs older than specified days."""
    if days < 7:
        raise HTTPException(status_code=400, detail="Minimum retention period is 7 days")
    if days > 365:
        raise HTTPException(status_code=400, detail="Maximum retention period is 365 days")

    async with AsyncSessionLocal() as session:
        repo = UsageRepository(session)
        deleted = await repo.cleanup_old_logs(days=days)
        return {"status": "ok", "deleted": deleted, "retention_days": days}


# =============================================================================
# Usage Limits Endpoints
# =============================================================================


@router.get("/limits")
async def admin_get_limits(
    enabled_only: bool = True,
    user: User = Depends(get_current_user),
):
    """Get all usage limits."""
    async with AsyncSessionLocal() as session:
        repo = UsageLimitsRepository(session)
        limits = await repo.get_all_limits(enabled_only=enabled_only)
        return {"limits": limits}


@router.get("/limits/{service_type}/{limit_type}")
async def admin_get_limit(
    service_type: str,
    limit_type: str,
    user: User = Depends(get_current_user),
):
    """Get a specific usage limit."""
    async with AsyncSessionLocal() as session:
        repo = UsageLimitsRepository(session)
        limit = await repo.get_limit(service_type, limit_type)
        if not limit:
            raise HTTPException(status_code=404, detail="Limit not found")
        return {"limit": limit}


@router.post("/limits")
async def admin_set_limit(
    request: UsageLimitRequest,
    user: User = Depends(get_current_user),
):
    """Create or update a usage limit."""
    if request.service_type not in ("tts", "stt", "llm"):
        raise HTTPException(status_code=400, detail="Invalid service_type. Must be: tts, stt, llm")
    if request.limit_type not in ("daily", "monthly"):
        raise HTTPException(status_code=400, detail="Invalid limit_type. Must be: daily, monthly")

    async with AsyncSessionLocal() as session:
        repo = UsageLimitsRepository(session)
        limit = await repo.set_limit(
            service_type=request.service_type,
            limit_type=request.limit_type,
            limit_value=request.limit_value,
            hard_limit=request.hard_limit,
            warning_threshold=request.warning_threshold,
        )
        return {"limit": limit}


@router.delete("/limits/{service_type}/{limit_type}")
async def admin_delete_limit(
    service_type: str,
    limit_type: str,
    user: User = Depends(get_current_user),
):
    """Delete a usage limit."""
    async with AsyncSessionLocal() as session:
        repo = UsageLimitsRepository(session)
        deleted = await repo.delete_limit(service_type, limit_type)
        if not deleted:
            raise HTTPException(status_code=404, detail="Limit not found")
        return {"status": "ok"}


# =============================================================================
# Usage Check Endpoint (for services)
# =============================================================================


@router.get("/check/{service_type}")
async def admin_check_usage(
    service_type: str,
    limit_type: str = "daily",
):
    """
    Check if usage is within limits.

    Called by services before processing requests.
    Returns whether the request should proceed or be blocked.
    """
    if service_type not in ("tts", "stt", "llm"):
        raise HTTPException(status_code=400, detail="Invalid service_type")

    async with AsyncSessionLocal() as session:
        usage_repo = UsageRepository(session)
        limits_repo = UsageLimitsRepository(session)

        # Get current usage for period
        current_usage = await usage_repo.get_period_usage(service_type, limit_type)

        # Check against limits
        check_result = await limits_repo.check_limit(service_type, current_usage)

        return {
            "service_type": service_type,
            "limit_type": limit_type,
            "current_usage": current_usage,
            **check_result,
        }


@router.get("/summary")
async def admin_get_usage_summary(
    user: User = Depends(get_current_user),
):
    """
    Get a summary of usage across all services.

    Includes current usage vs limits for quick dashboard display.
    """
    async with AsyncSessionLocal() as session:
        usage_repo = UsageRepository(session)
        limits_repo = UsageLimitsRepository(session)

        summary = {}
        for service in ("tts", "stt", "llm"):
            daily_usage = await usage_repo.get_period_usage(service, "daily")
            monthly_usage = await usage_repo.get_period_usage(service, "monthly")

            daily_limit = await limits_repo.get_limit(service, "daily")
            monthly_limit = await limits_repo.get_limit(service, "monthly")

            summary[service] = {
                "daily": {
                    "used": daily_usage,
                    "limit": daily_limit["limit_value"] if daily_limit else None,
                    "percent": round(daily_usage / daily_limit["limit_value"] * 100, 1)
                    if daily_limit and daily_limit["limit_value"] > 0
                    else 0,
                },
                "monthly": {
                    "used": monthly_usage,
                    "limit": monthly_limit["limit_value"] if monthly_limit else None,
                    "percent": round(monthly_usage / monthly_limit["limit_value"] * 100, 1)
                    if monthly_limit and monthly_limit["limit_value"] > 0
                    else 0,
                },
            }

        return {"summary": summary}
