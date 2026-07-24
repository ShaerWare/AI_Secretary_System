"""amoCRM integration router — OAuth flow, contacts, leads, pipelines, sync."""

import logging
import os
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.services.amocrm_service import (
    AmoCRMAPIError,
    add_note_to_lead,
    build_auth_url,
    create_contact,
    create_lead,
    exchange_code_for_token,
    get_account_info,
    get_all_leads_paginated,
    get_chat_history,
    get_contact_chats,
    get_contacts,
    get_contacts_by_ids,
    get_events,
    get_lead,
    get_leads,
    get_leads_by_pipeline,
    get_pipelines,
    get_unsorted_leads,
    get_users,
    refresh_access_token,
    send_chat_message,
    update_lead,
)
from app.services.crm_dataset_service import (
    CRM_DIR,
    build_pipeline_document,
    build_summary_document,
    clean_crm_files,
)
from auth_manager import User, require_permission, workspace_context
from db.redis_client import CacheKey, cache_delete_pattern, cache_get, cache_set
from modules.crm.service import amocrm_service
from modules.knowledge.service import knowledge_collection_service, knowledge_doc_service
from modules.monitoring.service import audit_service


# knowledge_collection_service and knowledge_doc_service are used only for
# read-only dataset-status queries; mutations go through DatasetSynced events.


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/crm", tags=["crm"])
webhook_router = APIRouter(tags=["amocrm-webhook"])


# ============== Helpers ==============


async def _get_valid_token(workspace_id: Optional[int] = None) -> dict:
    """Get config with a valid access token; auto-refresh if expired.

    Returns full config dict with fresh tokens.
    Raises HTTPException if not connected or refresh fails.
    """
    config = await amocrm_service.get_config_with_secrets(workspace_id=workspace_id)
    if not config or not config.get("access_token"):
        raise HTTPException(status_code=400, detail="amoCRM not connected")

    subdomain = config.get("subdomain", "")

    # Check if token expired
    expires_at = config.get("token_expires_at")
    token_expired = True
    if expires_at:
        if isinstance(expires_at, str):
            try:
                expires_at = datetime.fromisoformat(expires_at)
            except ValueError:
                expires_at = None
        if expires_at:
            # Refresh 5 minutes before expiry
            token_expired = datetime.utcnow() >= expires_at - timedelta(minutes=5)

    if token_expired:
        refresh_token = config.get("refresh_token")
        if not refresh_token:
            raise HTTPException(status_code=400, detail="No refresh token, re-authorize")

        try:
            tokens = await refresh_access_token(
                subdomain=subdomain,
                client_id=config.get("client_id", ""),
                client_secret=config.get("client_secret", ""),
                refresh_token=refresh_token,
                redirect_uri=config.get("redirect_uri", ""),
            )
        except AmoCRMAPIError as e:
            logger.error(f"Token refresh failed: {e}")
            raise HTTPException(status_code=401, detail="Token refresh failed, re-authorize")

        expires_in = tokens.get("expires_in", 86400)
        new_expires = datetime.utcnow() + timedelta(seconds=expires_in)

        await amocrm_service.save_config(
            workspace_id=workspace_id,
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            token_expires_at=new_expires,
        )

        config["access_token"] = tokens["access_token"]
        config["refresh_token"] = tokens["refresh_token"]
        config["token_expires_at"] = new_expires.isoformat()

    return config


def _get_subdomain(config: dict) -> str:
    """Extract subdomain from config for use in cache keys."""
    return config.get("subdomain", "unknown")


async def _invalidate_leads_cache(subdomain: str | None = None) -> None:
    """Invalidate all leads-related caches (pipeline leads + unsorted)."""
    await cache_delete_pattern(f"{CacheKey.AMOCRM}:pipeline_leads:*")
    await cache_delete_pattern(f"{CacheKey.AMOCRM}:unsorted:*")


# ============== Pydantic Models ==============


class AmoCRMConfigRequest(BaseModel):
    subdomain: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    redirect_uri: Optional[str] = None
    sync_contacts: Optional[bool] = None
    sync_leads: Optional[bool] = None
    sync_tasks: Optional[bool] = None
    auto_create_lead: Optional[bool] = None
    lead_pipeline_id: Optional[int] = None
    lead_status_id: Optional[int] = None
    amojo_base_url: Optional[str] = None
    amojo_scope_id: Optional[str] = None
    amojo_channel_secret: Optional[str] = None


class CreateContactRequest(BaseModel):
    name: str
    custom_fields: Optional[list] = None


class CreateLeadRequest(BaseModel):
    name: str
    pipeline_id: Optional[int] = None
    status_id: Optional[int] = None
    contact_id: Optional[int] = None


class AddNoteRequest(BaseModel):
    text: str


class UpdateLeadRequest(BaseModel):
    status_id: Optional[int] = None
    pipeline_id: Optional[int] = None
    name: Optional[str] = None
    price: Optional[int] = None


class SendChatMessageRequest(BaseModel):
    text: str
    sender_id: Optional[str] = "admin"
    sender_name: Optional[str] = "Admin"


# ============== Status & Config ==============


@router.get("/status")
async def crm_status(user: User = Depends(require_permission("sales", "view"))):
    """Quick status: connected? token expired? last sync."""
    _owner_id, ws_id = workspace_context(user, "sales")
    config = await amocrm_service.get_config(workspace_id=ws_id)
    if not config:
        return {
            "connected": False,
            "has_credentials": False,
            "last_sync": None,
        }

    return {
        "connected": config.get("is_connected", False),
        "has_credentials": bool(config.get("client_id")),
        "subdomain": config.get("subdomain"),
        "account_info": config.get("account_info"),
        "contacts_count": config.get("contacts_count", 0),
        "leads_count": config.get("leads_count", 0),
        "last_sync": config.get("last_sync_at"),
    }


@router.get("/config")
async def crm_get_config(user: User = Depends(require_permission("sales", "view"))):
    """Get amoCRM config (secrets masked)."""
    _owner_id, ws_id = workspace_context(user, "sales")
    config = await amocrm_service.get_config(workspace_id=ws_id)
    return {"config": config or {}}


@router.post("/config")
async def crm_save_config(
    request: AmoCRMConfigRequest,
    user: User = Depends(require_permission("sales", "manage")),
):
    """Save OAuth credentials and sync settings."""
    _owner_id, ws_id = workspace_context(user, "sales")
    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}
    config = await amocrm_service.save_config(workspace_id=ws_id, **kwargs)

    await audit_service.log(
        action="update",
        resource="amocrm_config",
        user_id=user.username,
        details={"fields": list(kwargs.keys())},
    )
    return {"status": "ok", "config": config}


# ============== OAuth Flow ==============


@router.get("/auth-url")
async def crm_auth_url(
    request: Request, user: User = Depends(require_permission("sales", "manage"))
):
    """Build OAuth authorization URL for amoCRM."""
    _owner_id, ws_id = workspace_context(user, "sales")
    config = await amocrm_service.get_config_with_secrets(workspace_id=ws_id)
    if not config or not config.get("client_id"):
        raise HTTPException(status_code=400, detail="Client ID not configured")

    subdomain = config.get("subdomain", "")
    if not subdomain:
        raise HTTPException(status_code=400, detail="Subdomain not configured")

    # Build redirect_uri: prefer saved, otherwise auto-detect
    redirect_uri = config.get("redirect_uri")
    if not redirect_uri:
        port = os.getenv("ORCHESTRATOR_PORT", "8002")
        redirect_uri = f"http://localhost:{port}/admin/crm/oauth-redirect"

    url = build_auth_url(
        subdomain=subdomain,
        client_id=config["client_id"],
        redirect_uri=redirect_uri,
    )
    return {"auth_url": url, "redirect_uri": redirect_uri}


@router.get("/oauth-redirect")
async def crm_oauth_redirect(
    code: Optional[str] = None,
    error: Optional[str] = None,
    referer: Optional[str] = None,
):
    """Server-side OAuth callback. amoCRM redirects here with ?code=...

    Exchanges code for tokens, saves, then redirects browser to admin panel.
    No JWT required — this is called by amoCRM redirect, not by the admin panel.
    """
    if error:
        logger.error(f"amoCRM OAuth error: {error}")
        return RedirectResponse(url="/admin/#/crm?error=oauth_denied")

    if not code:
        return RedirectResponse(url="/admin/#/crm?error=no_code")

    config = await amocrm_service.get_config_with_secrets()
    if not config:
        return RedirectResponse(url="/admin/#/crm?error=no_config")

    subdomain = config.get("subdomain", "")
    client_id = config.get("client_id", "")
    client_secret = config.get("client_secret", "")
    redirect_uri = config.get("redirect_uri", "")
    if not redirect_uri:
        port = os.getenv("ORCHESTRATOR_PORT", "8002")
        redirect_uri = f"http://localhost:{port}/admin/crm/oauth-redirect"

    try:
        tokens = await exchange_code_for_token(
            subdomain=subdomain,
            client_id=client_id,
            client_secret=client_secret,
            code=code,
            redirect_uri=redirect_uri,
        )
    except AmoCRMAPIError as e:
        logger.error(f"amoCRM token exchange failed: {e}")
        return RedirectResponse(url="/admin/#/crm?error=token_exchange_failed")

    # Save tokens
    expires_in = tokens.get("expires_in", 86400)
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    # Try to fetch account info
    account_info = {}
    try:
        account_info = await get_account_info(subdomain, tokens["access_token"])
    except Exception as e:
        logger.warning(f"Could not fetch account info: {e}")

    await amocrm_service.save_config(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        token_expires_at=expires_at,
        redirect_uri=redirect_uri,
        account_info=account_info,
    )

    await amocrm_service.log_sync(
        direction="incoming",
        entity_type="auth",
        action="connect",
        details={"account": account_info.get("name", "")},
    )

    return RedirectResponse(url="/admin/#/crm?connected=true")


@router.post("/disconnect")
async def crm_disconnect(user: User = Depends(require_permission("sales", "manage"))):
    """Clear tokens — disconnect from amoCRM."""
    _owner_id, ws_id = workspace_context(user, "sales")
    await amocrm_service.clear_tokens(workspace_id=ws_id)
    await cache_delete_pattern(f"{CacheKey.AMOCRM}:*")

    await audit_service.log(
        action="delete",
        resource="amocrm_config",
        resource_id="tokens",
        user_id=user.username,
    )

    await amocrm_service.log_sync(
        direction="outgoing",
        entity_type="auth",
        action="disconnect",
    )

    return {"status": "disconnected"}


@router.post("/test")
async def crm_test_connection(user: User = Depends(require_permission("sales", "edit"))):
    """Test connection by fetching account info."""
    _owner_id, ws_id = workspace_context(user, "sales")
    config = await _get_valid_token(workspace_id=ws_id)
    try:
        account = await get_account_info(config["subdomain"], config["access_token"])
        return {"status": "ok", "account": account}
    except AmoCRMAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/refresh-token")
async def crm_force_refresh_token(user: User = Depends(require_permission("sales", "manage"))):
    """Force token refresh."""
    _owner_id, ws_id = workspace_context(user, "sales")
    config = await amocrm_service.get_config_with_secrets(workspace_id=ws_id)
    if not config or not config.get("refresh_token"):
        raise HTTPException(status_code=400, detail="No refresh token available")

    try:
        tokens = await refresh_access_token(
            subdomain=config.get("subdomain", ""),
            client_id=config.get("client_id", ""),
            client_secret=config.get("client_secret", ""),
            refresh_token=config["refresh_token"],
            redirect_uri=config.get("redirect_uri", ""),
        )
    except AmoCRMAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    expires_in = tokens.get("expires_in", 86400)
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    await amocrm_service.save_config(
        workspace_id=ws_id,
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        token_expires_at=expires_at,
    )
    return {"status": "ok", "expires_at": expires_at.isoformat()}


# ============== Contacts ==============


@router.get("/contacts")
async def crm_get_contacts(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=250),
    query: Optional[str] = None,
    user: User = Depends(require_permission("sales", "view")),
):
    """List contacts from amoCRM (proxied)."""
    _owner_id, ws_id = workspace_context(user, "sales")
    config = await _get_valid_token(workspace_id=ws_id)
    try:
        data = await get_contacts(config["subdomain"], config["access_token"], page, limit, query)
        return data
    except AmoCRMAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/contacts")
async def crm_create_contact(
    request: CreateContactRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Create a contact in amoCRM."""
    _owner_id, ws_id = workspace_context(user, "sales")
    config = await _get_valid_token(workspace_id=ws_id)
    try:
        result = await create_contact(
            config["subdomain"],
            config["access_token"],
            name=request.name,
            custom_fields=request.custom_fields,
        )

        await amocrm_service.log_sync(
            direction="outgoing",
            entity_type="contact",
            action="create",
            details={"name": request.name},
        )

        return result
    except AmoCRMAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ============== Leads ==============


@router.get("/leads")
async def crm_get_leads(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=250),
    query: Optional[str] = None,
    user: User = Depends(require_permission("sales", "view")),
):
    """List leads from amoCRM (proxied)."""
    _owner_id, ws_id = workspace_context(user, "sales")
    config = await _get_valid_token(workspace_id=ws_id)
    try:
        data = await get_leads(config["subdomain"], config["access_token"], page, limit, query)
        return data
    except AmoCRMAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/leads")
async def crm_create_lead(
    request: CreateLeadRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Create a lead in amoCRM."""
    _owner_id, ws_id = workspace_context(user, "sales")
    config = await _get_valid_token(workspace_id=ws_id)
    try:
        result = await create_lead(
            config["subdomain"],
            config["access_token"],
            name=request.name,
            pipeline_id=request.pipeline_id,
            status_id=request.status_id,
            contact_id=request.contact_id,
        )

        # Invalidate pipeline leads and unsorted caches
        await _invalidate_leads_cache()

        await amocrm_service.log_sync(
            direction="outgoing",
            entity_type="lead",
            action="create",
            details={"name": request.name},
        )

        return result
    except AmoCRMAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/leads/{lead_id}/notes")
async def crm_add_note_to_lead(
    lead_id: int,
    request: AddNoteRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Add a note to a lead."""
    _owner_id, ws_id = workspace_context(user, "sales")
    config = await _get_valid_token(workspace_id=ws_id)
    try:
        result = await add_note_to_lead(
            config["subdomain"],
            config["access_token"],
            lead_id=lead_id,
            text=request.text,
        )
        return result
    except AmoCRMAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ============== Lead Detail & Update ==============


@router.get("/leads/by-pipeline/{pipeline_id}")
async def crm_get_leads_by_pipeline(
    pipeline_id: int,
    user: User = Depends(require_permission("sales", "view")),
):
    """Get all leads in a specific pipeline (for kanban board)."""
    _owner_id, ws_id = workspace_context(user, "sales")
    config = await _get_valid_token(workspace_id=ws_id)
    subdomain = _get_subdomain(config)
    cache_key = f"{CacheKey.AMOCRM}:pipeline_leads:{subdomain}:{pipeline_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        data = await get_leads_by_pipeline(config["subdomain"], config["access_token"], pipeline_id)
        await cache_set(cache_key, data, ttl_seconds=60)
        return data
    except AmoCRMAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.get("/leads/unsorted")
async def crm_get_unsorted_leads(
    page: int = 1,
    limit: int = 250,
    user: User = Depends(require_permission("sales", "view")),
):
    """Get unsorted (incoming) leads, paginated."""
    _owner_id, ws_id = workspace_context(user, "sales")
    config = await _get_valid_token(workspace_id=ws_id)
    subdomain = _get_subdomain(config)
    cache_key = f"{CacheKey.AMOCRM}:unsorted:{subdomain}:{page}:{limit}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        data = await get_unsorted_leads(
            config["subdomain"], config["access_token"], page=page, limit=limit
        )
        await cache_set(cache_key, data, ttl_seconds=30)
        return data
    except AmoCRMAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.get("/triage")
async def crm_triage(
    limit: int = 20,
    user: User = Depends(require_permission("sales", "view")),
):
    """Triage unanswered (unsorted) leads: routing + priced matches + action.

    Returns {ok:false, reason:"reauth_needed"} when the amoCRM token is dead —
    re-authorize via GET /admin/crm/auth-url.
    """
    _owner_id, ws_id = workspace_context(user, "sales")
    try:
        config = await _get_valid_token(workspace_id=ws_id)
    except HTTPException as e:
        return {
            "ok": False,
            "reason": "reauth_needed",
            "detail": e.detail,
            "auth_hint": "Переавторизуйте amoCRM: GET /admin/crm/auth-url → открыть auth_url",
        }
    from modules.crm.triage import triage_unanswered

    try:
        return await triage_unanswered(config, limit=limit)
    except AmoCRMAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.get("/leads/{lead_id}")
async def crm_get_lead(
    lead_id: int,
    user: User = Depends(require_permission("sales", "view")),
):
    """Get single lead detail with contacts."""
    _owner_id, ws_id = workspace_context(user, "sales")
    config = await _get_valid_token(workspace_id=ws_id)
    subdomain = _get_subdomain(config)
    cache_key = f"{CacheKey.AMOCRM}:lead:{subdomain}:{lead_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        data = await get_lead(
            config["subdomain"], config["access_token"], lead_id, with_contacts=True
        )
        await cache_set(cache_key, data, ttl_seconds=120)
        return data
    except AmoCRMAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.patch("/leads/{lead_id}")
async def crm_update_lead(
    lead_id: int,
    request: UpdateLeadRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Update a lead (status, pipeline, name, price)."""
    _owner_id, ws_id = workspace_context(user, "sales")
    config = await _get_valid_token(workspace_id=ws_id)
    update_data = {k: v for k, v in request.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        result = await update_lead(
            config["subdomain"], config["access_token"], lead_id, update_data
        )

        # Invalidate caches for this lead and pipeline views
        await cache_delete_pattern(f"{CacheKey.AMOCRM}:lead:*:{lead_id}")
        await _invalidate_leads_cache()

        await amocrm_service.log_sync(
            direction="outgoing",
            entity_type="lead",
            entity_id=lead_id,
            action="update",
            details=update_data,
        )

        return result
    except AmoCRMAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ============== Events ==============


@router.get("/events")
async def crm_get_events(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    types: Optional[str] = None,
    user: User = Depends(require_permission("sales", "view")),
):
    """Get events feed (chat messages, lead changes, etc.)."""
    _owner_id, ws_id = workspace_context(user, "sales")
    config = await _get_valid_token(workspace_id=ws_id)
    try:
        data = await get_events(config["subdomain"], config["access_token"], page, limit, types)
        return data
    except AmoCRMAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ============== Contact Chats ==============


@router.get("/contacts/{contact_id}/chats")
async def crm_get_contact_chats(
    contact_id: int,
    user: User = Depends(require_permission("sales", "view")),
):
    """Get chats linked to a contact."""
    _owner_id, ws_id = workspace_context(user, "sales")
    config = await _get_valid_token(workspace_id=ws_id)
    try:
        data = await get_contact_chats(config["subdomain"], config["access_token"], contact_id)
        return data
    except AmoCRMAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ============== Chat Messages (amojo API) ==============


@router.get("/chats/{chat_id}/history")
async def crm_get_chat_history(
    chat_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("sales", "view")),
):
    """Get chat message history via amojo API."""
    _owner_id, ws_id = workspace_context(user, "sales")
    config = await amocrm_service.get_config_with_secrets(workspace_id=ws_id)
    if not config:
        raise HTTPException(status_code=400, detail="amoCRM not configured")

    amojo_base_url = config.get("amojo_base_url", "https://amojo.amocrm.ru")
    scope_id = config.get("amojo_scope_id")
    channel_secret = config.get("amojo_channel_secret")

    if not scope_id or not channel_secret:
        raise HTTPException(status_code=400, detail="Amojo inbox not configured")

    try:
        data = await get_chat_history(
            amojo_base_url, scope_id, channel_secret, chat_id, limit, offset
        )
        return data
    except AmoCRMAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/chats/{chat_id}/messages")
async def crm_send_chat_message(
    chat_id: str,
    request: SendChatMessageRequest,
    user: User = Depends(require_permission("sales", "edit")),
):
    """Send a chat message via amojo API."""
    _owner_id, ws_id = workspace_context(user, "sales")
    config = await amocrm_service.get_config_with_secrets(workspace_id=ws_id)
    if not config:
        raise HTTPException(status_code=400, detail="amoCRM not configured")

    amojo_base_url = config.get("amojo_base_url", "https://amojo.amocrm.ru")
    scope_id = config.get("amojo_scope_id")
    channel_secret = config.get("amojo_channel_secret")

    if not scope_id or not channel_secret:
        raise HTTPException(status_code=400, detail="Amojo inbox not configured")

    try:
        result = await send_chat_message(
            amojo_base_url,
            scope_id,
            channel_secret,
            chat_id,
            sender_id=request.sender_id or "admin",
            sender_name=request.sender_name or "Admin",
            text=request.text,
        )

        await amocrm_service.log_sync(
            direction="outgoing",
            entity_type="chat",
            action="send_message",
            details={"chat_id": chat_id, "text_length": len(request.text)},
        )

        return result
    except AmoCRMAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ============== Pipelines ==============


@router.get("/pipelines")
async def crm_get_pipelines(user: User = Depends(require_permission("sales", "view"))):
    """List pipelines with their statuses."""
    _owner_id, ws_id = workspace_context(user, "sales")
    config = await _get_valid_token(workspace_id=ws_id)
    subdomain = _get_subdomain(config)
    cache_key = f"{CacheKey.AMOCRM}:pipelines:{subdomain}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        data = await get_pipelines(config["subdomain"], config["access_token"])
        await cache_set(cache_key, data, ttl_seconds=300)
        return data
    except AmoCRMAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ============== Sync ==============


@router.post("/sync")
async def crm_sync(user: User = Depends(require_permission("sales", "edit"))):
    """Manual sync — fetch counts from amoCRM and update local stats."""
    _owner_id, ws_id = workspace_context(user, "sales")
    config = await _get_valid_token(workspace_id=ws_id)
    subdomain = config["subdomain"]
    access_token = config["access_token"]

    contacts_count = 0
    leads_count = 0

    try:
        contacts_full = await get_contacts(subdomain, access_token, page=1, limit=250)
        contacts_list = (contacts_full or {}).get("_embedded", {}).get("contacts", [])
        contacts_count = len(contacts_list)
    except AmoCRMAPIError:
        pass

    try:
        leads_full = await get_leads(subdomain, access_token, page=1, limit=250)
        leads_list = (leads_full or {}).get("_embedded", {}).get("leads", [])
        leads_count = len(leads_list)
    except AmoCRMAPIError:
        pass

    await amocrm_service.save_config(
        workspace_id=ws_id,
        contacts_count=contacts_count,
        leads_count=leads_count,
        last_sync_at=datetime.utcnow(),
    )

    await amocrm_service.log_sync(
        direction="incoming",
        entity_type="sync",
        action="sync",
        details={"contacts": contacts_count, "leads": leads_count},
    )

    return {
        "status": "ok",
        "contacts_count": contacts_count,
        "leads_count": leads_count,
        "synced_at": datetime.utcnow().isoformat(),
    }


@router.get("/sync-log")
async def crm_sync_log(
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_permission("sales", "view")),
):
    """Get sync event log."""
    logs = await amocrm_service.get_sync_logs(limit)
    return {"logs": logs}


# ============== CRM Dataset (Knowledge Base Sync) ==============


CRM_FILE_PREFIX = "crm-"


@router.post("/dataset-sync")
async def crm_dataset_sync(user: User = Depends(require_permission("sales", "edit"))):
    """Sync amoCRM data into knowledge base for RAG.

    Fetches all pipelines + leads, generates markdown documents,
    writes to data/crm-dataset/, updates knowledge collection + re-indexes.
    """
    _owner_id, ws_id = workspace_context(user, "sales")
    config = await _get_valid_token(workspace_id=ws_id)
    subdomain = config["subdomain"]
    access_token = config["access_token"]

    sync_time = datetime.utcnow().strftime("%d.%m.%Y %H:%M")

    # 1. Fetch pipelines
    pipelines_data = await get_pipelines(subdomain, access_token)
    pipelines = (pipelines_data or {}).get("_embedded", {}).get("pipelines", [])
    if not pipelines:
        raise HTTPException(status_code=400, detail="No pipelines found in amoCRM")

    # Build status maps: pipeline_id -> {status_id -> status_name}
    status_maps: dict[int, dict[int, str]] = {}
    for p in pipelines:
        smap: dict[int, str] = {}
        for s in (p.get("_embedded") or {}).get("statuses", []):
            smap[s["id"]] = s["name"]
        status_maps[p["id"]] = smap

    # 2. Fetch all leads with contacts
    all_leads = await get_all_leads_paginated(subdomain, access_token)

    # 2a. Collect unique contact IDs from all leads for enrichment
    contact_ids: set[int] = set()
    for lead in all_leads:
        for c in (lead.get("_embedded") or {}).get("contacts", []):
            if c.get("id"):
                contact_ids.add(c["id"])

    # 2b. Batch-fetch full contacts (with phone/email)
    contacts_map: dict[int, dict] = {}
    if contact_ids:
        try:
            contacts_map = await get_contacts_by_ids(subdomain, access_token, list(contact_ids))
        except Exception as e:
            logger.warning(f"CRM dataset: failed to enrich contacts: {e}")

    # 2c. Fetch users for responsible_user_id resolution
    users_map: dict[int, str] = {}
    try:
        users_map = await get_users(subdomain, access_token)
    except Exception as e:
        logger.warning(f"CRM dataset: failed to fetch users: {e}")

    # Group leads by pipeline
    pipeline_leads: dict[int, list[dict]] = {p["id"]: [] for p in pipelines}
    for lead in all_leads:
        pid = lead.get("pipeline_id")
        if pid in pipeline_leads:
            pipeline_leads[pid].append(lead)

    # 3. Clean old CRM files
    removed = clean_crm_files()

    # 4. Generate and write documents
    CRM_DIR.mkdir(parents=True, exist_ok=True)
    written_files: list[tuple[str, str, str]] = []  # (filename, content, title)

    for pipeline in pipelines:
        pid = pipeline["id"]
        leads = pipeline_leads.get(pid, [])
        content = build_pipeline_document(
            pipeline, leads, status_maps.get(pid, {}), sync_time, contacts_map, users_map
        )
        filename = f"{CRM_FILE_PREFIX}pipeline-{pid}.md"
        filepath = CRM_DIR / filename
        filepath.write_text(content, encoding="utf-8")
        written_files.append((filename, content, f"Воронка: {pipeline.get('name', '')}"))

    # Summary document
    summary_content = build_summary_document(
        pipelines, pipeline_leads, status_maps, sync_time, contacts_map, users_map
    )
    summary_filename = f"{CRM_FILE_PREFIX}summary.md"
    (CRM_DIR / summary_filename).write_text(summary_content, encoding="utf-8")
    written_files.append((summary_filename, summary_content, "amoCRM: Сводка по сделкам"))

    # 5. Publish DatasetSynced event — knowledge domain handles DB + RAG
    from app.dependencies import get_container
    from modules.core.events import DatasetSynced

    documents = []
    for filename, content, title in written_files:
        sections = len(re.findall(r"^#{2,3}\s+.+$", content, re.MULTILINE))
        documents.append(
            {
                "filename": filename,
                "title": title,
                "source_type": "amocrm",
                "file_size_bytes": len(content.encode("utf-8")),
                "section_count": sections,
            }
        )

    try:
        await get_container().event_bus.publish(
            DatasetSynced(
                source="amocrm",
                collection_slug="amocrm",
                action="synced",
                collection_name="amoCRM",
                collection_description="Данные из amoCRM: сделки, контакты, воронки (автосинхронизация)",
                base_dir=str(CRM_DIR),
                documents=documents,
            )
        )
    except Exception as e:
        logger.warning("Failed to publish DatasetSynced: %s", e)

    # Resolve collection_id for response (read-only)
    collection = await knowledge_collection_service.get_by_slug("amocrm")
    collection_id = collection["id"] if collection else None

    # 6. Log sync event
    await amocrm_service.log_sync(
        direction="incoming",
        entity_type="dataset",
        action="sync",
        details={
            "pipelines": len(pipelines),
            "leads": len(all_leads),
            "contacts_enriched": len(contacts_map),
            "users_resolved": len(users_map),
            "files_written": len(written_files),
            "files_removed": len(removed),
            "collection_id": collection_id,
        },
    )

    await audit_service.log(
        action="dataset_sync",
        resource="amocrm",
        user_id=user.username,
        details={
            "leads": len(all_leads),
            "pipelines": len(pipelines),
            "files": len(written_files),
        },
    )

    return {
        "status": "ok",
        "pipelines": len(pipelines),
        "leads_total": len(all_leads),
        "contacts_enriched": len(contacts_map),
        "users_resolved": len(users_map),
        "files_written": len(written_files),
        "files_removed": len(removed),
        "collection_id": collection_id,
        "synced_at": sync_time,
    }


@router.get("/dataset-status")
async def crm_dataset_status(user: User = Depends(require_permission("sales", "view"))):
    """Get CRM dataset sync status."""
    collection = await knowledge_collection_service.get_by_slug("amocrm")
    if not collection:
        return {
            "synced": False,
            "collection_id": None,
            "documents": 0,
            "total_sections": 0,
            "last_sync": None,
            "files": [],
        }

    docs = await knowledge_doc_service.get_by_collection(collection["id"])

    # Find last dataset sync in sync log
    logs = await amocrm_service.get_sync_logs(limit=20)
    last_dataset_sync = None
    for log_entry in logs:
        if log_entry.get("entity_type") == "dataset" and log_entry.get("action") == "sync":
            last_dataset_sync = log_entry.get("created")
            break

    return {
        "synced": len(docs) > 0,
        "collection_id": collection["id"],
        "collection_name": collection["name"],
        "documents": len(docs),
        "total_sections": sum(d.get("section_count", 0) for d in docs),
        "last_sync": last_dataset_sync,
        "files": [d["filename"] for d in docs],
    }


@router.delete("/dataset")
async def crm_dataset_clear(user: User = Depends(require_permission("sales", "manage"))):
    """Clear CRM dataset — remove files, DB records, and collection index."""
    removed = clean_crm_files()

    from app.dependencies import get_container
    from modules.core.events import DatasetSynced

    try:
        await get_container().event_bus.publish(
            DatasetSynced(
                source="amocrm",
                collection_slug="amocrm",
                action="cleared",
                base_dir=str(CRM_DIR),
            )
        )
    except Exception as e:
        logger.warning("Failed to publish DatasetSynced(cleared): %s", e)

    return {"status": "ok", "files_removed": len(removed)}


# ============== Webhook (public) ==============


@webhook_router.post("/webhooks/amocrm")
async def amocrm_webhook(request: Request):
    """Handle incoming amoCRM webhook.

    amoCRM sends POST with form-encoded data for events like:
    contacts[add], contacts[update], leads[add], leads[status], etc.
    """
    try:
        content_type = request.headers.get("content-type", "")

        if "application/json" in content_type:
            data = await request.json()
        else:
            # Form-encoded
            form = await request.form()
            data = dict(form)

        logger.info(
            f"amoCRM webhook received: {list(data.keys()) if isinstance(data, dict) else 'raw'}"
        )

        # Invalidate caches on lead-related webhook events
        if isinstance(data, dict):
            lead_keys = [k for k in data if k.startswith("leads[")]
            if lead_keys:
                await cache_delete_pattern(f"{CacheKey.AMOCRM}:pipeline_leads:*")
                await cache_delete_pattern(f"{CacheKey.AMOCRM}:unsorted:*")
                await cache_delete_pattern(f"{CacheKey.AMOCRM}:lead:*")

        await amocrm_service.log_sync(
            direction="incoming",
            entity_type="webhook",
            action="receive",
            details=data if isinstance(data, dict) else {"raw": str(data)[:500]},
        )

        return {"status": "ok"}
    except Exception as e:
        logger.error(f"amoCRM webhook error: {e}")
        return {"status": "error", "detail": str(e)}
