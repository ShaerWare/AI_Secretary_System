"""Outbound approval queue + channel monitoring (`/admin/outbound/*`).

Surfaced on the CRM page: the operator sees what the assistant wants to say,
edits or rejects it, and watches whether the channels are alive at all.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth_manager import User, require_permission
from modules.monitoring.service import audit_service
from modules.outbound.service import OutboundError, outbound_service


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/outbound", tags=["outbound"])


class SubmitRequest(BaseModel):
    channel: str
    instance_id: str
    target: str
    text: str
    session_id: Optional[str] = None
    client_text: Optional[str] = None


class TextRequest(BaseModel):
    text: str


class ApproveRequest(BaseModel):
    text: Optional[str] = None


class SettingsRequest(BaseModel):
    instances: Optional[dict[str, dict[str, Any]]] = None
    unanswered_minutes: Optional[int] = None
    pending_alert_minutes: Optional[int] = None


def _http(e: OutboundError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=str(e))


@router.post("/submit")
async def outbound_submit(
    request: SubmitRequest,
    user: User = Depends(require_permission("chat", "edit")),
):
    """Called by channel processes with a freshly generated reply."""
    return await outbound_service.submit(
        channel=request.channel,
        instance_id=request.instance_id,
        target=request.target,
        text=request.text,
        session_id=request.session_id,
        client_text=request.client_text,
    )


@router.get("/messages")
async def outbound_list(
    status: Optional[str] = Query(
        None, description="pending | sent | rejected | failed, через запятую"
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("sales", "view")),
):
    return await outbound_service.list_messages(status=status, limit=limit, offset=offset)


@router.get("/messages/{message_id}")
async def outbound_get(
    message_id: int,
    user: User = Depends(require_permission("sales", "view")),
):
    message = await outbound_service.get(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Сообщение не найдено")
    return {"message": message}


@router.put("/messages/{message_id}")
async def outbound_update(
    message_id: int,
    request: TextRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    try:
        return {"message": await outbound_service.update_text(message_id, request.text)}
    except OutboundError as e:
        raise _http(e) from e


@router.post("/messages/{message_id}/approve")
async def outbound_approve(
    message_id: int,
    request: ApproveRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    try:
        message = await outbound_service.approve(message_id, user.username, text=request.text)
    except OutboundError as e:
        raise _http(e) from e
    await audit_service.log(
        action="approve",
        resource="outbound",
        resource_id=str(message_id),
        user_id=user.username,
        details={"status": message["status"], "edited": message["edited"]},
    )
    return {"message": message}


@router.post("/messages/{message_id}/reject")
async def outbound_reject(
    message_id: int,
    user: User = Depends(require_permission("sales", "edit")),
):
    try:
        message = await outbound_service.reject(message_id, user.username)
    except OutboundError as e:
        raise _http(e) from e
    await audit_service.log(
        action="reject",
        resource="outbound",
        resource_id=str(message_id),
        user_id=user.username,
    )
    return {"message": message}


@router.delete("/messages/{message_id}")
async def outbound_delete(
    message_id: int,
    user: User = Depends(require_permission("sales", "manage")),
):
    try:
        deleted = await outbound_service.delete(message_id)
    except OutboundError as e:
        raise _http(e) from e
    if not deleted:
        raise HTTPException(status_code=404, detail="Сообщение не найдено")
    return {"status": "ok"}


@router.get("/settings")
async def outbound_settings(user: User = Depends(require_permission("sales", "view"))):
    return await outbound_service.get_settings()


@router.put("/settings")
async def outbound_save_settings(
    request: SettingsRequest,
    user: User = Depends(require_permission("sales", "manage")),
):
    try:
        settings = await outbound_service.save_settings(request.model_dump(exclude_none=True))
    except OutboundError as e:
        raise _http(e) from e
    await audit_service.log(
        action="update",
        resource="outbound_settings",
        user_id=user.username,
        details=settings,
    )
    return settings


@router.get("/monitor")
async def outbound_monitor(user: User = Depends(require_permission("sales", "view"))):
    return await outbound_service.monitor()
