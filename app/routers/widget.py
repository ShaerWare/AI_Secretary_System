# app/routers/widget.py
"""Widget router - legacy config, instances CRUD."""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.cors_middleware import get_cors_middleware
from auth_manager import User, require_permission, user_has_level, workspace_context
from db.integration import (
    async_audit_logger,
    async_config_manager,
    async_resource_share_manager,
    async_widget_instance_manager,
)


def _invalidate_cors_cache() -> None:
    """Invalidate CORS cache so widget domain changes take effect immediately."""
    mw = get_cors_middleware()
    if mw:
        mw.invalidate_cache()


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/widget", tags=["widget"])


# ============== Pydantic Models ==============


class AdminWidgetConfigRequest(BaseModel):
    enabled: bool = False
    title: str = ""
    greeting: str = ""
    placeholder: str = ""
    primary_color: str = "#c2410c"
    position: str = "right"
    allowed_domains: List[str] = []
    tunnel_url: str = ""


class WidgetInstanceCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    enabled: bool = True
    title: str = "AI Ассистент"
    greeting: str = "Здравствуйте! Чем могу помочь?"
    placeholder: str = "Введите сообщение..."
    placeholder_color: str = ""
    placeholder_font: str = ""
    primary_color: str = "#c2410c"
    button_icon: str = "chat"
    position: str = "right"
    allowed_domains: List[str] = []
    tunnel_url: Optional[str] = None
    llm_backend: str = "vllm"
    llm_persona: str = "anna"
    system_prompt: Optional[str] = None
    llm_params: Optional[dict] = None
    tts_engine: str = "xtts"
    tts_voice: str = "anna"
    tts_preset: Optional[str] = None


class WidgetInstanceUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    title: Optional[str] = None
    greeting: Optional[str] = None
    placeholder: Optional[str] = None
    placeholder_color: Optional[str] = None
    placeholder_font: Optional[str] = None
    primary_color: Optional[str] = None
    button_icon: Optional[str] = None
    position: Optional[str] = None
    allowed_domains: Optional[List[str]] = None
    tunnel_url: Optional[str] = None
    llm_backend: Optional[str] = None
    llm_persona: Optional[str] = None
    system_prompt: Optional[str] = None
    llm_params: Optional[dict] = None
    tts_engine: Optional[str] = None
    tts_voice: Optional[str] = None
    tts_preset: Optional[str] = None
    rate_limit_count: Optional[int] = None
    rate_limit_hours: Optional[int] = None


class WidgetShareRequest(BaseModel):
    user_id: int
    permission: str = "view"


class WidgetUpdateShareRequest(BaseModel):
    permission: str


RESOURCE_TYPE_WIDGET = "widget_instance"


async def _check_widget_owner_or_admin(instance_id: str, user: User) -> dict:
    """Verify user is owner or admin of the widget instance."""
    owner_id, ws_id = workspace_context(user, "channels")
    instance = await async_widget_instance_manager.get_instance(
        instance_id, owner_id=owner_id, workspace_id=ws_id
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Widget instance not found")
    is_admin = user_has_level(user, "channels", "manage")
    is_owner = instance.get("owner_id") == user.id
    if not is_admin and not is_owner:
        raise HTTPException(status_code=403, detail="Only owner or admin can manage shares")
    return instance


async def _check_widget_share_edit_permission(instance_id: str, user: User) -> None:
    """Check if shared user has edit permission."""
    is_admin = user_has_level(user, "channels", "manage")
    if is_admin:
        return
    perm = await async_resource_share_manager.get_user_permission(
        RESOURCE_TYPE_WIDGET, instance_id, user.id
    )
    if perm == "view":
        raise HTTPException(status_code=403, detail="View-only access — editing not allowed")


# ============== Legacy Config Endpoints ==============


@router.get("/config")
async def admin_get_widget_config(user: User = Depends(require_permission("channels", "view"))):
    """Получить конфигурацию виджета (legacy endpoint - uses 'default' instance)"""
    # Try to get from default instance first
    instance = await async_widget_instance_manager.get_instance("default")
    if instance:
        # Convert instance format to legacy config format
        config = {
            "enabled": instance.get("enabled", False),
            "title": instance.get("title", ""),
            "greeting": instance.get("greeting", ""),
            "placeholder": instance.get("placeholder", ""),
            "primary_color": instance.get("primary_color", "#c2410c"),
            "position": instance.get("position", "right"),
            "allowed_domains": instance.get("allowed_domains", []),
            "tunnel_url": instance.get("tunnel_url", ""),
        }
    else:
        # Fallback to legacy config
        config = await async_config_manager.get_widget()
    return {"config": config}


@router.post("/config")
async def admin_save_widget_config(
    request: AdminWidgetConfigRequest, user: User = Depends(require_permission("channels", "edit"))
):
    """Сохранить конфигурацию виджета (legacy endpoint - saves to 'default' instance)"""
    config = {
        "enabled": request.enabled,
        "title": request.title,
        "greeting": request.greeting,
        "placeholder": request.placeholder,
        "primary_color": request.primary_color,
        "position": request.position,
        "allowed_domains": request.allowed_domains,
        "tunnel_url": request.tunnel_url,
    }

    # Save to legacy config (backward compatibility)
    await async_config_manager.set_widget(config)

    # Also save to 'default' widget instance
    existing_instance = await async_widget_instance_manager.get_instance("default")
    if existing_instance:
        await async_widget_instance_manager.update_instance("default", **config)
    else:
        # Create default instance if it doesn't exist
        await async_widget_instance_manager.create_instance(
            name="Default Widget", description="Default widget (legacy)", id="default", **config
        )

    _invalidate_cors_cache()

    # Audit log
    await async_audit_logger.log(
        action="update",
        resource="config",
        resource_id="widget",
        user_id=user.username,
        details={"enabled": config["enabled"], "title": config["title"]},
    )

    return {"status": "ok", "config": config}


# ============== Widget Instances Endpoints ==============


@router.get("/instances")
async def admin_list_widget_instances(
    enabled_only: bool = False, user: User = Depends(require_permission("channels", "view"))
):
    """List all widget instances"""
    owner_id, ws_id = workspace_context(user, "channels")
    instances = await async_widget_instance_manager.list_instances(
        enabled_only=enabled_only, owner_id=owner_id, workspace_id=ws_id
    )

    # Enrich with share info
    instance_ids = [i["id"] for i in instances]
    share_counts = await async_resource_share_manager.get_share_counts(
        RESOURCE_TYPE_WIDGET, instance_ids
    )
    shared_with_me = {}
    if owner_id is not None:
        shared_with_me = await async_resource_share_manager.get_shared_resources_with_permissions(
            RESOURCE_TYPE_WIDGET, owner_id
        )
    for instance in instances:
        iid = instance["id"]
        instance["share_count"] = share_counts.get(iid, 0)
        instance["is_shared_with_me"] = iid in shared_with_me
        instance["share_permission"] = shared_with_me.get(iid)

    return {"instances": instances}


@router.post("/instances")
async def admin_create_widget_instance(
    request: WidgetInstanceCreateRequest,
    user: User = Depends(require_permission("channels", "edit")),
):
    """Create a new widget instance"""
    owner_id, ws_id = workspace_context(user, "channels")
    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}
    kwargs["owner_id"] = owner_id
    kwargs["workspace_id"] = ws_id

    instance = await async_widget_instance_manager.create_instance(**kwargs)

    _invalidate_cors_cache()

    # Audit log
    await async_audit_logger.log(
        action="create",
        resource="widget_instance",
        resource_id=instance["id"],
        user_id=user.username,
        details={"name": instance["name"]},
    )

    return {"instance": instance}


@router.get("/instances/{instance_id}")
async def admin_get_widget_instance(
    instance_id: str, user: User = Depends(require_permission("channels", "view"))
):
    """Get a specific widget instance"""
    owner_id, ws_id = workspace_context(user, "channels")
    instance = await async_widget_instance_manager.get_instance(
        instance_id, owner_id=owner_id, workspace_id=ws_id
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Widget instance not found")

    return {"instance": instance}


@router.put("/instances/{instance_id}")
async def admin_update_widget_instance(
    instance_id: str,
    request: WidgetInstanceUpdateRequest,
    user: User = Depends(require_permission("channels", "edit")),
):
    """Update a widget instance"""
    owner_id, ws_id = workspace_context(user, "channels")
    existing = await async_widget_instance_manager.get_instance(
        instance_id, owner_id=owner_id, workspace_id=ws_id
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Widget instance not found")

    # Shared users need edit permission
    await _check_widget_share_edit_permission(instance_id, user)

    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}

    instance = await async_widget_instance_manager.update_instance(instance_id, **kwargs)

    _invalidate_cors_cache()

    # Audit log
    await async_audit_logger.log(
        action="update",
        resource="widget_instance",
        resource_id=instance_id,
        user_id=user.username,
        details={"name": instance.get("name")},
    )

    return {"instance": instance}


@router.delete("/instances/{instance_id}")
async def admin_delete_widget_instance(
    instance_id: str, user: User = Depends(require_permission("channels", "edit"))
):
    """Delete a widget instance — only owner or admin"""
    owner_id, ws_id = workspace_context(user, "channels")
    success = await async_widget_instance_manager.delete_instance(
        instance_id, owner_id=owner_id, workspace_id=ws_id
    )
    if not success:
        raise HTTPException(status_code=404, detail="Widget instance not found")

    # Clean up shares
    await async_resource_share_manager.remove_all_shares(RESOURCE_TYPE_WIDGET, instance_id)

    _invalidate_cors_cache()

    # Audit log
    await async_audit_logger.log(
        action="delete", resource="widget_instance", resource_id=instance_id, user_id=user.username
    )

    return {"status": "ok", "message": f"Widget instance {instance_id} deleted"}


# ============== Resource Sharing Endpoints ==============


@router.get("/instances/{instance_id}/shares")
async def get_widget_shares(
    instance_id: str, user: User = Depends(require_permission("channels", "view"))
):
    """List shares for a widget instance."""
    await _check_widget_owner_or_admin(instance_id, user)
    shares = await async_resource_share_manager.get_shares(RESOURCE_TYPE_WIDGET, instance_id)
    return {"shares": shares}


@router.post("/instances/{instance_id}/shares")
async def add_widget_share(
    instance_id: str,
    request: WidgetShareRequest,
    user: User = Depends(require_permission("channels", "edit")),
):
    """Share a widget instance with another user."""
    await _check_widget_owner_or_admin(instance_id, user)

    if request.permission not in ("view", "edit"):
        raise HTTPException(status_code=400, detail="Permission must be 'view' or 'edit'")
    if request.user_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot share with yourself")

    share = await async_resource_share_manager.add_share(
        RESOURCE_TYPE_WIDGET,
        instance_id,
        request.user_id,
        request.permission,
        shared_by=user.id,
    )

    await async_audit_logger.log(
        action="share",
        resource="widget_instance",
        resource_id=instance_id,
        user_id=user.username,
        details={"shared_with": request.user_id, "permission": request.permission},
    )

    return {"share": share}


@router.put("/instances/{instance_id}/shares/{target_user_id}")
async def update_widget_share(
    instance_id: str,
    target_user_id: int,
    request: WidgetUpdateShareRequest,
    user: User = Depends(require_permission("channels", "edit")),
):
    """Update share permission for a widget instance."""
    await _check_widget_owner_or_admin(instance_id, user)

    if request.permission not in ("view", "edit"):
        raise HTTPException(status_code=400, detail="Permission must be 'view' or 'edit'")

    success = await async_resource_share_manager.update_permission(
        RESOURCE_TYPE_WIDGET, instance_id, target_user_id, request.permission
    )
    if not success:
        raise HTTPException(status_code=404, detail="Share not found")

    return {"status": "ok"}


@router.delete("/instances/{instance_id}/shares/{target_user_id}")
async def remove_widget_share(
    instance_id: str,
    target_user_id: int,
    user: User = Depends(require_permission("channels", "edit")),
):
    """Remove a share from a widget instance."""
    await _check_widget_owner_or_admin(instance_id, user)

    success = await async_resource_share_manager.remove_share(
        RESOURCE_TYPE_WIDGET, instance_id, target_user_id
    )
    if not success:
        raise HTTPException(status_code=404, detail="Share not found")

    await async_audit_logger.log(
        action="unshare",
        resource="widget_instance",
        resource_id=instance_id,
        user_id=user.username,
        details={"removed_user": target_user_id},
    )

    return {"status": "ok"}
