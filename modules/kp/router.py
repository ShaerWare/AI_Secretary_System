"""КП: approval, delivery and timers (`/admin/kp/*`) + PIM webhook.

Shown on the CRM page, tab «КП». WhatsApp КП also appear in the approval queue
(tab «Подтверждение»); approving in either place is the same operation.
"""

import hmac
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

from auth_manager import User, require_permission
from modules.kp.service import KpError, kp_service
from modules.monitoring.service import audit_service


logger = logging.getLogger(__name__)

# Usernames of the internal sessions issued to bot subprocesses
# (multi_bot_manager.py, whatsapp_manager.py).
INTERNAL_BOT_USERS = ("__internal_bot__", "__internal_wa_bot__")

router = APIRouter(prefix="/admin/kp", tags=["kp"])
webhook_router = APIRouter(prefix="/webhooks", tags=["kp"])


class QuoteRequest(BaseModel):
    customer: dict[str, Any]
    items: list[dict[str, Any]]
    valid_days: Optional[int] = None
    delivery: str = "link"
    channel_instance_id: Optional[str] = None
    target: Optional[str] = None
    email: Optional[str] = None
    message: Optional[str] = None
    request_number: Optional[str] = None
    session_id: Optional[str] = None
    note: Optional[str] = None


class FromDialogueRequest(BaseModel):
    session_id: str


class ApproveRequest(BaseModel):
    text: Optional[str] = None


class ReissueRequest(BaseModel):
    valid_days: Optional[int] = None
    refresh_prices: bool = False


class OutcomeRequest(BaseModel):
    status: str
    note: str = ""


class RejectRequest(BaseModel):
    note: str = ""


def _http(e: KpError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=str(e))


async def _audit(action: str, user: User, quote_id: Any = None, details: Optional[dict] = None):
    await audit_service.log(
        action=action,
        resource="kp",
        resource_id=str(quote_id) if quote_id is not None else None,
        user_id=user.username,
        details=details,
    )


# ─── Connection + settings ────────────────────────────────────


@router.get("/status")
async def kp_status(user: User = Depends(require_permission("sales", "view"))):
    return await kp_service.status()


@router.get("/settings")
async def kp_settings(user: User = Depends(require_permission("sales", "view"))):
    return await kp_service.get_settings()


@router.put("/settings")
async def kp_save_settings(
    data: dict[str, Any], user: User = Depends(require_permission("sales", "edit"))
):
    try:
        settings = await kp_service.save_settings(data)
    except KpError as e:
        raise _http(e) from e
    await _audit("update", user, details={"settings": list(data)})
    return settings


@router.post("/sync")
async def kp_sync(user: User = Depends(require_permission("sales", "edit"))):
    """Pull statuses from the PIM and run the timers now."""
    result = await kp_service.sync_from_pim()
    result["timers"] = await kp_service.run_timers()
    return result


# ─── Quotes ───────────────────────────────────────────────────


@router.get("/quotes")
async def kp_list(
    status: Optional[str] = Query(None, description="Статусы через запятую"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("sales", "view")),
):
    return await kp_service.list_quotes(status=status, limit=limit, offset=offset)


@router.get("/quotes/{quote_id}")
async def kp_get(quote_id: int, user: User = Depends(require_permission("sales", "view"))):
    try:
        return {"quote": await kp_service.get_quote(quote_id)}
    except KpError as e:
        raise _http(e) from e


@router.get("/quotes/{quote_id}/pdf")
async def kp_pdf(quote_id: int, user: User = Depends(require_permission("sales", "view"))):
    try:
        content = await kp_service.pdf(quote_id)
    except KpError as e:
        raise _http(e) from e
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="kp-{quote_id}.pdf"'},
    )


@router.post("/quotes")
async def kp_create(
    request: QuoteRequest, user: User = Depends(require_permission("sales", "edit"))
):
    try:
        quote = await kp_service.create_quote(request.model_dump(), created_by=user.username)
    except KpError as e:
        raise _http(e) from e
    await _audit("create", user, quote["id"], {"number": quote["number"]})
    return {"quote": quote}


@router.post("/quotes/from-dialogue")
async def kp_from_dialogue(
    request: FromDialogueRequest,
    req: Request,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Draft a КП from a chat: what the client asked for, matched to the catalog."""
    from app.dependencies import get_container

    llm = get_container().llm_service
    try:
        quote = await kp_service.create_from_dialogue(
            request.session_id, llm, created_by=user.username, origin="manual"
        )
    except KpError as e:
        raise _http(e) from e
    await _audit("create", user, quote["id"], {"number": quote["number"], "from": "dialogue"})
    return {"quote": quote}


@router.put("/quotes/{quote_id}")
async def kp_update(
    quote_id: int,
    data: dict[str, Any],
    user: User = Depends(require_permission("sales", "edit")),
):
    try:
        quote = await kp_service.update_quote(quote_id, data, user.username)
    except KpError as e:
        raise _http(e) from e
    await _audit("update", user, quote_id, {"fields": list(data)})
    return {"quote": quote}


@router.post("/quotes/{quote_id}/approve")
async def kp_approve(
    quote_id: int,
    request: ApproveRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    try:
        quote = await kp_service.approve(quote_id, user.username, text=request.text)
    except KpError as e:
        raise _http(e) from e
    await _audit("approve", user, quote_id, {"status": quote["status"]})
    return {"quote": quote}


@router.post("/quotes/{quote_id}/reject")
async def kp_reject(
    quote_id: int,
    request: RejectRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    try:
        quote = await kp_service.reject(quote_id, user.username, request.note)
    except KpError as e:
        raise _http(e) from e
    await _audit("reject", user, quote_id)
    return {"quote": quote}


@router.post("/quotes/{quote_id}/reissue")
async def kp_reissue(
    quote_id: int,
    request: ReissueRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    try:
        quote = await kp_service.reissue(
            quote_id,
            user.username,
            valid_days=request.valid_days,
            refresh_prices=request.refresh_prices,
        )
    except KpError as e:
        raise _http(e) from e
    await _audit("reissue", user, quote_id, {"new_id": quote["id"], "number": quote["number"]})
    return {"quote": quote}


@router.post("/quotes/{quote_id}/outcome")
async def kp_outcome(
    quote_id: int,
    request: OutcomeRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    try:
        quote = await kp_service.set_outcome(quote_id, request.status, user.username, request.note)
    except KpError as e:
        raise _http(e) from e
    await _audit("outcome", user, quote_id, {"status": request.status})
    return {"quote": quote}


@router.delete("/quotes/{quote_id}")
async def kp_delete(quote_id: int, user: User = Depends(require_permission("sales", "manage"))):
    try:
        deleted = await kp_service.delete(quote_id)
    except KpError as e:
        raise _http(e) from e
    if not deleted:
        raise HTTPException(status_code=404, detail="КП не найдено")
    await _audit("delete", user, quote_id)
    return {"status": "ok"}


# ─── Timers ───────────────────────────────────────────────────


@router.get("/rules")
async def kp_rules(user: User = Depends(require_permission("sales", "view"))):
    return {"rules": await kp_service.list_rules()}


@router.post("/rules")
async def kp_rule_create(
    data: dict[str, Any], user: User = Depends(require_permission("sales", "edit"))
):
    try:
        rule = await kp_service.create_rule(data)
    except KpError as e:
        raise _http(e) from e
    await audit_service.log(
        action="create", resource="kp_rule", resource_id=str(rule["id"]), user_id=user.username
    )
    return {"rule": rule}


@router.put("/rules/{rule_id}")
async def kp_rule_update(
    rule_id: int,
    data: dict[str, Any],
    user: User = Depends(require_permission("sales", "edit")),
):
    try:
        rule = await kp_service.update_rule(rule_id, data)
    except KpError as e:
        raise _http(e) from e
    await audit_service.log(
        action="update", resource="kp_rule", resource_id=str(rule_id), user_id=user.username
    )
    return {"rule": rule}


@router.delete("/rules/{rule_id}")
async def kp_rule_delete(rule_id: int, user: User = Depends(require_permission("sales", "edit"))):
    if not await kp_service.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="Таймер не найден")
    await audit_service.log(
        action="delete", resource="kp_rule", resource_id=str(rule_id), user_id=user.username
    )
    return {"status": "ok"}


@router.get("/events")
async def kp_events(
    unread: bool = False,
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_permission("sales", "view")),
):
    return {"events": await kp_service.list_events(unread_only=unread, limit=limit)}


@router.post("/events/{event_id}/ack")
async def kp_event_ack(event_id: int, user: User = Depends(require_permission("sales", "edit"))):
    try:
        return {"event": await kp_service.ack_event(event_id, user.username)}
    except KpError as e:
        raise _http(e) from e


# ─── Staff commands from the WhatsApp bot (modules/kp/messenger.py) ───


class StaffMessageRequest(BaseModel):
    sender: str
    phone: Optional[str] = None
    text: str


@router.post("/staff-message")
async def kp_staff_message(
    request: StaffMessageRequest, user: User = Depends(require_permission("chat", "edit"))
):
    """The WhatsApp bot asks: is this a manager's command? Answers ``handled`` + reply.

    Only bot processes may call it — the sender's number is their word, and an
    approval must not be forgeable by any panel user typing a staff number.
    """
    if user.username not in INTERNAL_BOT_USERS:
        raise HTTPException(status_code=403, detail="Только для процессов ботов")
    from modules.kp.messenger import handle_staff_whatsapp

    return await handle_staff_whatsapp(request.sender, request.phone, request.text)


class TelegramUpdateRequest(BaseModel):
    update: dict[str, Any]


@router.post("/telegram-update")
async def kp_telegram_update(
    request: TelegramUpdateRequest, user: User = Depends(require_permission("chat", "edit"))
):
    """A Telegram bot process forwards a КП button press / reply it received."""
    if user.username not in INTERNAL_BOT_USERS:
        raise HTTPException(status_code=403, detail="Только для процессов ботов")
    from modules.kp.messenger import handle_telegram_update, telegram_target

    token, chat_id = telegram_target(await kp_service.get_settings())
    if not token or not chat_id:
        return {"handled": False}
    return {"handled": await handle_telegram_update(request.update, token, chat_id)}


# ─── PIM webhook (docs/pim-api-for-kp.md) ─────────────────────


@webhook_router.post("/pim")
async def pim_webhook(request: Request):
    secret = (os.getenv("ARGS_PIM_WEBHOOK_SECRET") or "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="PIM webhook is not configured")
    given = request.headers.get("X-Webhook-Secret", "")
    if not hmac.compare_digest(given.encode(), secret.encode()):
        raise HTTPException(status_code=401, detail="Bad webhook secret")
    try:
        payload = await request.json()
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid JSON") from e
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Expected a JSON object")
    return await kp_service.handle_webhook(payload)
