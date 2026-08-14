# modules/channels/whatsapp/router.py
"""WhatsApp bot router - instances CRUD, bot control, logs."""

import logging
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth_manager import User, require_permission, user_has_level, workspace_context
from modules.admin.service import resource_share_service
from modules.channels.whatsapp.bridge import (
    bridge_webhook_url,
    get_bridge_client,
    is_bridge_instance,
    resolve_bridge_url,
)
from modules.channels.whatsapp.service import whatsapp_instance_service
from modules.monitoring.service import audit_service
from whatsapp_manager import whatsapp_manager


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/whatsapp", tags=["whatsapp"])


# ============== Pydantic Models ==============


class WhatsAppInstanceCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    enabled: bool = True
    auto_start: bool = False
    # Transport: "cloud" (Meta Cloud API) or "bridge" (self-hosted, QR-linked phone)
    provider: str = "cloud"
    bridge_url: Optional[str] = None
    bridge_token: Optional[str] = None
    # WhatsApp Cloud API
    phone_number_id: str = ""
    waba_id: Optional[str] = None
    access_token: Optional[str] = None
    verify_token: Optional[str] = None
    app_secret: Optional[str] = None
    # Webhook
    webhook_port: int = 8003
    # AI
    llm_backend: str = "vllm"
    system_prompt: Optional[str] = None
    llm_params: Optional[dict] = None
    # TTS
    tts_enabled: bool = False
    tts_engine: str = "xtts"
    tts_voice: str = "anna"
    tts_preset: Optional[str] = None
    # Access control
    allowed_phones: List[str] = []
    blocked_phones: List[str] = []
    # Rate limiting
    rate_limit_count: Optional[int] = None
    rate_limit_hours: Optional[int] = None


class WhatsAppInstanceUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    auto_start: Optional[bool] = None
    # Transport
    provider: Optional[str] = None
    bridge_url: Optional[str] = None
    bridge_token: Optional[str] = None
    # WhatsApp Cloud API
    phone_number_id: Optional[str] = None
    waba_id: Optional[str] = None
    access_token: Optional[str] = None
    verify_token: Optional[str] = None
    app_secret: Optional[str] = None
    # Webhook
    webhook_port: Optional[int] = None
    # AI
    llm_backend: Optional[str] = None
    system_prompt: Optional[str] = None
    llm_params: Optional[dict] = None
    # TTS
    tts_enabled: Optional[bool] = None
    tts_engine: Optional[str] = None
    tts_voice: Optional[str] = None
    tts_preset: Optional[str] = None
    # Access control
    allowed_phones: Optional[List[str]] = None
    blocked_phones: Optional[List[str]] = None
    # Rate limiting
    rate_limit_count: Optional[int] = None
    rate_limit_hours: Optional[int] = None
    # RAG
    rag_mode: Optional[str] = None
    knowledge_collection_ids: Optional[List[int]] = None


class WhatsAppShareRequest(BaseModel):
    user_id: int
    permission: str = "view"


class WhatsAppUpdateShareRequest(BaseModel):
    permission: str


RESOURCE_TYPE_WHATSAPP = "whatsapp_instance"


async def _check_wa_owner_or_admin(instance_id: str, user: User) -> dict:
    """Verify user is owner or admin of the WhatsApp instance."""
    owner_id, ws_id = workspace_context(user, "channels")
    instance = await whatsapp_instance_service.get_instance(
        instance_id, owner_id=owner_id, workspace_id=ws_id
    )
    if not instance:
        raise HTTPException(status_code=404, detail="WhatsApp instance not found")
    is_admin = user_has_level(user, "channels", "manage")
    is_owner = instance.get("owner_id") == user.id
    if not is_admin and not is_owner:
        raise HTTPException(status_code=403, detail="Only owner or admin can manage shares")
    return instance


async def _check_wa_share_edit_permission(instance_id: str, user: User) -> None:
    """Check if shared user has edit permission."""
    is_admin = user_has_level(user, "channels", "manage")
    if is_admin:
        return
    perm = await resource_share_service.get_user_permission(
        RESOURCE_TYPE_WHATSAPP, instance_id, user.id
    )
    if perm == "view":
        raise HTTPException(status_code=403, detail="View-only access — editing not allowed")


# ============== Instance Endpoints ==============


@router.get("/instances")
async def list_whatsapp_instances(
    enabled_only: bool = False, user: User = Depends(require_permission("channels", "view"))
):
    """List all WhatsApp bot instances."""
    owner_id, ws_id = workspace_context(user, "channels")
    instances = await whatsapp_instance_service.list_instances(
        enabled_only=enabled_only, owner_id=owner_id, workspace_id=ws_id
    )

    # Add running status from whatsapp_manager
    statuses = await whatsapp_manager.get_all_statuses()
    for instance in instances:
        instance["running"] = statuses.get(instance["id"], {}).get("running", False)

    # Enrich with share info
    instance_ids = [i["id"] for i in instances]
    share_counts = await resource_share_service.get_share_counts(
        RESOURCE_TYPE_WHATSAPP, instance_ids
    )
    shared_with_me = {}
    if owner_id is not None:
        shared_with_me = await resource_share_service.get_shared_resources_with_permissions(
            RESOURCE_TYPE_WHATSAPP, owner_id
        )
    for instance in instances:
        iid = instance["id"]
        instance["share_count"] = share_counts.get(iid, 0)
        instance["is_shared_with_me"] = iid in shared_with_me
        instance["share_permission"] = shared_with_me.get(iid)

    return {"instances": instances}


@router.post("/instances")
async def create_whatsapp_instance(
    request: WhatsAppInstanceCreateRequest,
    user: User = Depends(require_permission("channels", "edit")),
):
    """Create a new WhatsApp bot instance."""
    owner_id, ws_id = workspace_context(user, "channels")
    # Convert request to dict, removing None values
    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}
    kwargs["owner_id"] = owner_id
    kwargs["workspace_id"] = ws_id

    instance = await whatsapp_instance_service.create_instance(**kwargs)

    # Audit log
    await audit_service.log(
        action="create",
        resource="whatsapp_instance",
        resource_id=instance["id"],
        user_id=user.username,
        details={"name": instance["name"]},
    )

    return {"instance": instance}


@router.get("/instances/{instance_id}")
async def get_whatsapp_instance(
    instance_id: str,
    include_token: bool = False,
    user: User = Depends(require_permission("channels", "view")),
):
    """Get a specific WhatsApp bot instance."""
    owner_id, ws_id = workspace_context(user, "channels")
    if include_token:
        instance = await whatsapp_instance_service.get_instance_with_token(instance_id)
    else:
        instance = await whatsapp_instance_service.get_instance(
            instance_id, owner_id=owner_id, workspace_id=ws_id
        )

    if not instance:
        raise HTTPException(status_code=404, detail="WhatsApp instance not found")

    # Add running status
    status = await whatsapp_manager.get_bot_status(instance_id)
    instance["running"] = status.get("running", False)
    instance["pid"] = status.get("pid")

    return {"instance": instance}


@router.put("/instances/{instance_id}")
async def update_whatsapp_instance(
    instance_id: str,
    request: WhatsAppInstanceUpdateRequest,
    user: User = Depends(require_permission("channels", "edit")),
):
    """Update a WhatsApp bot instance."""
    # Check if exists and verify ownership
    owner_id, ws_id = workspace_context(user, "channels")
    existing = await whatsapp_instance_service.get_instance(
        instance_id, owner_id=owner_id, workspace_id=ws_id
    )
    if not existing:
        raise HTTPException(status_code=404, detail="WhatsApp instance not found")

    # Shared users need edit permission
    await _check_wa_share_edit_permission(instance_id, user)

    # Convert request to dict, removing None values
    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}

    instance = await whatsapp_instance_service.update_instance(instance_id, **kwargs)

    # Audit log
    await audit_service.log(
        action="update",
        resource="whatsapp_instance",
        resource_id=instance_id,
        user_id=user.username,
        details={"name": instance.get("name") if instance else None},
    )

    return {"instance": instance}


@router.delete("/instances/{instance_id}")
async def delete_whatsapp_instance(
    instance_id: str, user: User = Depends(require_permission("channels", "edit"))
):
    """Delete a WhatsApp bot instance — only owner or admin."""
    owner_id, ws_id = workspace_context(user, "channels")
    # Stop bot if running
    await whatsapp_manager.stop_bot(instance_id)

    success = await whatsapp_instance_service.delete_instance(
        instance_id, owner_id=owner_id, workspace_id=ws_id
    )
    if not success:
        raise HTTPException(status_code=404, detail="WhatsApp instance not found")

    # Clean up shares
    await resource_share_service.remove_all_shares(RESOURCE_TYPE_WHATSAPP, instance_id)

    # Audit log
    await audit_service.log(
        action="delete",
        resource="whatsapp_instance",
        resource_id=instance_id,
        user_id=user.username,
    )

    return {"status": "ok", "message": f"WhatsApp instance {instance_id} deleted"}


# ============== Bot Control Endpoints ==============


@router.post("/instances/{instance_id}/start")
async def start_whatsapp_instance(
    instance_id: str, user: User = Depends(require_permission("channels", "edit"))
):
    """Start a specific WhatsApp bot instance and enable auto-start."""
    # Workspace gate-check
    instance = await whatsapp_instance_service.get_instance(
        instance_id, workspace_id=user.workspace_id
    )
    if not instance:
        raise HTTPException(status_code=404, detail="WhatsApp instance not found")

    # Shared users need edit permission
    await _check_wa_share_edit_permission(instance_id, user)

    # Re-fetch with token for start logic
    instance = await whatsapp_instance_service.get_instance_with_token(instance_id)

    if not instance.get("enabled"):
        raise HTTPException(status_code=400, detail="WhatsApp instance is disabled")

    result = await whatsapp_manager.start_bot(instance_id)

    # Save auto_start=True so bot restarts on app launch
    if result.get("status") in ["started", "already_running"]:
        await whatsapp_instance_service.set_auto_start(instance_id, True)

    return result


@router.post("/instances/{instance_id}/stop")
async def stop_whatsapp_instance(
    instance_id: str, user: User = Depends(require_permission("channels", "edit"))
):
    """Stop a specific WhatsApp bot instance and disable auto-start."""
    # Workspace gate-check
    instance = await whatsapp_instance_service.get_instance(
        instance_id, workspace_id=user.workspace_id
    )
    if not instance:
        raise HTTPException(status_code=404, detail="WhatsApp instance not found")

    # Shared users need edit permission
    await _check_wa_share_edit_permission(instance_id, user)

    result = await whatsapp_manager.stop_bot(instance_id)

    # Save auto_start=False so bot doesn't restart on app launch
    if result.get("status") == "stopped":
        await whatsapp_instance_service.set_auto_start(instance_id, False)

    return result


@router.post("/instances/{instance_id}/restart")
async def restart_whatsapp_instance(
    instance_id: str, user: User = Depends(require_permission("channels", "edit"))
):
    """Restart a specific WhatsApp bot instance."""
    # Workspace gate-check
    instance = await whatsapp_instance_service.get_instance(
        instance_id, workspace_id=user.workspace_id
    )
    if not instance:
        raise HTTPException(status_code=404, detail="WhatsApp instance not found")

    # Shared users need edit permission
    await _check_wa_share_edit_permission(instance_id, user)

    result = await whatsapp_manager.restart_bot(instance_id)
    return result


@router.get("/instances/{instance_id}/status")
async def get_whatsapp_instance_status(
    instance_id: str, user: User = Depends(require_permission("channels", "view"))
):
    """Get status of a specific WhatsApp bot instance."""
    owner_id, ws_id = workspace_context(user, "channels")
    instance = await whatsapp_instance_service.get_instance(
        instance_id, owner_id=owner_id, workspace_id=ws_id
    )
    if not instance:
        raise HTTPException(status_code=404, detail="WhatsApp instance not found")

    status = await whatsapp_manager.get_bot_status(instance_id)

    return {
        "status": {
            **status,
            "enabled": instance.get("enabled", False),
        }
    }


@router.get("/instances/{instance_id}/logs")
async def get_whatsapp_instance_logs(
    instance_id: str, lines: int = 100, user: User = Depends(require_permission("channels", "view"))
):
    """Get recent logs for a WhatsApp bot instance."""
    owner_id, ws_id = workspace_context(user, "channels")
    instance = await whatsapp_instance_service.get_instance(
        instance_id, owner_id=owner_id, workspace_id=ws_id
    )
    if not instance:
        raise HTTPException(status_code=404, detail="WhatsApp instance not found")

    logs = await whatsapp_manager.get_recent_logs(instance_id, lines=lines)
    return {"logs": logs}


# ============== Self-hosted bridge (QR linking) ==============


async def _get_bridge_instance(instance_id: str, user: User, *, edit: bool) -> dict:
    """Fetch an instance for a bridge operation, enforcing workspace + share ACLs."""
    owner_id, ws_id = workspace_context(user, "channels")
    instance = await whatsapp_instance_service.get_instance(
        instance_id, owner_id=owner_id if not edit else None, workspace_id=ws_id
    )
    if not instance:
        raise HTTPException(status_code=404, detail="WhatsApp instance not found")

    if edit:
        await _check_wa_share_edit_permission(instance_id, user)

    if not is_bridge_instance(instance):
        raise HTTPException(
            status_code=400,
            detail="Instance is not using the self-hosted provider (provider='bridge')",
        )

    # Re-fetch with secrets so a per-instance bridge token is honoured.
    full = await whatsapp_instance_service.get_instance_with_token(instance_id)
    return full or instance


async def _bridge_call(instance: dict, action: str) -> dict:
    """Run one bridge operation, mapping transport failures to clean HTTP errors."""
    client = get_bridge_client(instance)
    try:
        if action == "start":
            # Pressing "Подключить телефон" is an explicit request to link, so a
            # dead credential set is discarded and pairing starts clean.
            return await client.start_session(bridge_webhook_url(instance), force=True)
        if action == "status":
            return await client.get_status()
        if action == "stop":
            return await client.stop_session()
        if action == "logout":
            return await client.logout()
        raise ValueError(f"unknown bridge action: {action}")
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:500]
        if e.response.status_code == 401:
            detail = "Bridge rejected the token (check WHATSAPP_BRIDGE_TOKEN)"
        raise HTTPException(status_code=502, detail=f"Bridge error: {detail}") from e
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=503,
            detail=(
                f"WhatsApp bridge is unreachable at {resolve_bridge_url(instance)} "
                f"({type(e).__name__}). Is services/whatsapp-bridge running?"
            ),
        ) from e
    finally:
        await client.close()


@router.post("/instances/{instance_id}/bridge/start")
async def start_bridge_session(
    instance_id: str, user: User = Depends(require_permission("channels", "edit"))
):
    """Open the bridge session — returns a QR to scan when the phone isn't linked yet."""
    instance = await _get_bridge_instance(instance_id, user, edit=True)
    state = await _bridge_call(instance, "start")

    await audit_service.log(
        action="bridge_start",
        resource="whatsapp_instance",
        resource_id=instance_id,
        user_id=user.username,
        details={"status": state.get("status")},
    )
    return state


@router.get("/instances/{instance_id}/bridge/status")
async def get_bridge_session_status(
    instance_id: str, user: User = Depends(require_permission("channels", "view"))
):
    """Link state of the phone: idle / starting / qr / connected / disconnected / logged_out.

    While the status is ``qr`` the response carries a ``qr`` data-URL to render.
    """
    instance = await _get_bridge_instance(instance_id, user, edit=False)
    return await _bridge_call(instance, "status")


@router.post("/instances/{instance_id}/bridge/stop")
async def stop_bridge_session(
    instance_id: str, user: User = Depends(require_permission("channels", "edit"))
):
    """Close the socket but keep credentials — a later start re-attaches without a QR."""
    instance = await _get_bridge_instance(instance_id, user, edit=True)
    return await _bridge_call(instance, "stop")


@router.post("/instances/{instance_id}/bridge/logout")
async def logout_bridge_session(
    instance_id: str, user: User = Depends(require_permission("channels", "edit"))
):
    """Unlink the phone and wipe credentials. The next start requires a fresh QR scan."""
    instance = await _get_bridge_instance(instance_id, user, edit=True)
    state = await _bridge_call(instance, "logout")

    await audit_service.log(
        action="bridge_logout",
        resource="whatsapp_instance",
        resource_id=instance_id,
        user_id=user.username,
    )
    return state


# ============== Resource Sharing Endpoints ==============


@router.get("/instances/{instance_id}/shares")
async def get_whatsapp_shares(
    instance_id: str, user: User = Depends(require_permission("channels", "view"))
):
    """List shares for a WhatsApp instance."""
    await _check_wa_owner_or_admin(instance_id, user)
    shares = await resource_share_service.get_shares(RESOURCE_TYPE_WHATSAPP, instance_id)
    return {"shares": shares}


@router.post("/instances/{instance_id}/shares")
async def add_whatsapp_share(
    instance_id: str,
    request: WhatsAppShareRequest,
    user: User = Depends(require_permission("channels", "edit")),
):
    """Share a WhatsApp instance with another user."""
    await _check_wa_owner_or_admin(instance_id, user)

    if request.permission not in ("view", "edit"):
        raise HTTPException(status_code=400, detail="Permission must be 'view' or 'edit'")
    if request.user_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot share with yourself")

    share = await resource_share_service.add_share(
        RESOURCE_TYPE_WHATSAPP,
        instance_id,
        request.user_id,
        request.permission,
        shared_by=user.id,
    )

    await audit_service.log(
        action="share",
        resource="whatsapp_instance",
        resource_id=instance_id,
        user_id=user.username,
        details={"shared_with": request.user_id, "permission": request.permission},
    )

    return {"share": share}


@router.put("/instances/{instance_id}/shares/{target_user_id}")
async def update_whatsapp_share(
    instance_id: str,
    target_user_id: int,
    request: WhatsAppUpdateShareRequest,
    user: User = Depends(require_permission("channels", "edit")),
):
    """Update share permission for a WhatsApp instance."""
    await _check_wa_owner_or_admin(instance_id, user)

    if request.permission not in ("view", "edit"):
        raise HTTPException(status_code=400, detail="Permission must be 'view' or 'edit'")

    success = await resource_share_service.update_permission(
        RESOURCE_TYPE_WHATSAPP, instance_id, target_user_id, request.permission
    )
    if not success:
        raise HTTPException(status_code=404, detail="Share not found")

    return {"status": "ok"}


@router.delete("/instances/{instance_id}/shares/{target_user_id}")
async def remove_whatsapp_share(
    instance_id: str,
    target_user_id: int,
    user: User = Depends(require_permission("channels", "edit")),
):
    """Remove a share from a WhatsApp instance."""
    await _check_wa_owner_or_admin(instance_id, user)

    success = await resource_share_service.remove_share(
        RESOURCE_TYPE_WHATSAPP, instance_id, target_user_id
    )
    if not success:
        raise HTTPException(status_code=404, detail="Share not found")

    await audit_service.log(
        action="unshare",
        resource="whatsapp_instance",
        resource_id=instance_id,
        user_id=user.username,
        details={"removed_user": target_user_id},
    )

    return {"status": "ok"}
