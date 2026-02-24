# app/routers/whatsapp.py
"""WhatsApp bot router - instances CRUD, bot control, logs."""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth_manager import User, require_permission, workspace_context
from db.integration import async_audit_logger, async_whatsapp_instance_manager
from whatsapp_manager import whatsapp_manager


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/whatsapp", tags=["whatsapp"])


# ============== Pydantic Models ==============


class WhatsAppInstanceCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    enabled: bool = True
    auto_start: bool = False
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


# ============== Instance Endpoints ==============


@router.get("/instances")
async def list_whatsapp_instances(
    enabled_only: bool = False, user: User = Depends(require_permission("channels", "view"))
):
    """List all WhatsApp bot instances."""
    owner_id, ws_id = workspace_context(user, "channels")
    instances = await async_whatsapp_instance_manager.list_instances(
        enabled_only=enabled_only, owner_id=owner_id, workspace_id=ws_id
    )

    # Add running status from whatsapp_manager
    statuses = await whatsapp_manager.get_all_statuses()
    for instance in instances:
        instance["running"] = statuses.get(instance["id"], {}).get("running", False)

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

    instance = await async_whatsapp_instance_manager.create_instance(**kwargs)

    # Audit log
    await async_audit_logger.log(
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
        instance = await async_whatsapp_instance_manager.get_instance_with_token(instance_id)
    else:
        instance = await async_whatsapp_instance_manager.get_instance(
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
    existing = await async_whatsapp_instance_manager.get_instance(
        instance_id, owner_id=owner_id, workspace_id=ws_id
    )
    if not existing:
        raise HTTPException(status_code=404, detail="WhatsApp instance not found")

    # Convert request to dict, removing None values
    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}

    instance = await async_whatsapp_instance_manager.update_instance(instance_id, **kwargs)

    # Audit log
    await async_audit_logger.log(
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
    """Delete a WhatsApp bot instance."""
    owner_id, ws_id = workspace_context(user, "channels")
    # Stop bot if running
    await whatsapp_manager.stop_bot(instance_id)

    success = await async_whatsapp_instance_manager.delete_instance(
        instance_id, owner_id=owner_id, workspace_id=ws_id
    )
    if not success:
        raise HTTPException(status_code=404, detail="WhatsApp instance not found")

    # Audit log
    await async_audit_logger.log(
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
    instance = await async_whatsapp_instance_manager.get_instance(
        instance_id, workspace_id=user.workspace_id
    )
    if not instance:
        raise HTTPException(status_code=404, detail="WhatsApp instance not found")

    # Re-fetch with token for start logic
    instance = await async_whatsapp_instance_manager.get_instance_with_token(instance_id)

    if not instance.get("enabled"):
        raise HTTPException(status_code=400, detail="WhatsApp instance is disabled")

    result = await whatsapp_manager.start_bot(instance_id)

    # Save auto_start=True so bot restarts on app launch
    if result.get("status") in ["started", "already_running"]:
        await async_whatsapp_instance_manager.set_auto_start(instance_id, True)

    return result


@router.post("/instances/{instance_id}/stop")
async def stop_whatsapp_instance(
    instance_id: str, user: User = Depends(require_permission("channels", "edit"))
):
    """Stop a specific WhatsApp bot instance and disable auto-start."""
    # Workspace gate-check
    instance = await async_whatsapp_instance_manager.get_instance(
        instance_id, workspace_id=user.workspace_id
    )
    if not instance:
        raise HTTPException(status_code=404, detail="WhatsApp instance not found")

    result = await whatsapp_manager.stop_bot(instance_id)

    # Save auto_start=False so bot doesn't restart on app launch
    if result.get("status") == "stopped":
        await async_whatsapp_instance_manager.set_auto_start(instance_id, False)

    return result


@router.post("/instances/{instance_id}/restart")
async def restart_whatsapp_instance(
    instance_id: str, user: User = Depends(require_permission("channels", "edit"))
):
    """Restart a specific WhatsApp bot instance."""
    # Workspace gate-check
    instance = await async_whatsapp_instance_manager.get_instance(
        instance_id, workspace_id=user.workspace_id
    )
    if not instance:
        raise HTTPException(status_code=404, detail="WhatsApp instance not found")

    result = await whatsapp_manager.restart_bot(instance_id)
    return result


@router.get("/instances/{instance_id}/status")
async def get_whatsapp_instance_status(
    instance_id: str, user: User = Depends(require_permission("channels", "view"))
):
    """Get status of a specific WhatsApp bot instance."""
    owner_id, ws_id = workspace_context(user, "channels")
    instance = await async_whatsapp_instance_manager.get_instance(
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
    instance = await async_whatsapp_instance_manager.get_instance(
        instance_id, owner_id=owner_id, workspace_id=ws_id
    )
    if not instance:
        raise HTTPException(status_code=404, detail="WhatsApp instance not found")

    logs = await whatsapp_manager.get_recent_logs(instance_id, lines=lines)
    return {"logs": logs}
