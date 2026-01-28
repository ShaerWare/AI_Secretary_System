# app/routers/widget.py
"""Widget router - legacy config, instances CRUD."""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth_manager import User, get_current_user
from db.integration import (
    async_audit_logger,
    async_config_manager,
    async_widget_instance_manager,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/widget", tags=["widget"])


# ============== Pydantic Models ==============


class AdminWidgetConfigRequest(BaseModel):
    enabled: bool = False
    title: str = ""
    greeting: str = ""
    placeholder: str = ""
    primary_color: str = "#6366f1"
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
    primary_color: str = "#6366f1"
    position: str = "right"
    allowed_domains: List[str] = []
    tunnel_url: Optional[str] = None
    llm_backend: str = "vllm"
    llm_persona: str = "gulya"
    system_prompt: Optional[str] = None
    llm_params: Optional[dict] = None
    tts_engine: str = "xtts"
    tts_voice: str = "gulya"
    tts_preset: Optional[str] = None


class WidgetInstanceUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    title: Optional[str] = None
    greeting: Optional[str] = None
    placeholder: Optional[str] = None
    primary_color: Optional[str] = None
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


# ============== Legacy Config Endpoints ==============


@router.get("/config")
async def admin_get_widget_config():
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
            "primary_color": instance.get("primary_color", "#6366f1"),
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
    request: AdminWidgetConfigRequest, user: User = Depends(get_current_user)
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
async def admin_list_widget_instances(enabled_only: bool = False):
    """List all widget instances"""
    instances = await async_widget_instance_manager.list_instances(enabled_only=enabled_only)
    return {"instances": instances}


@router.post("/instances")
async def admin_create_widget_instance(
    request: WidgetInstanceCreateRequest, user: User = Depends(get_current_user)
):
    """Create a new widget instance"""
    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}

    instance = await async_widget_instance_manager.create_instance(**kwargs)

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
async def admin_get_widget_instance(instance_id: str):
    """Get a specific widget instance"""
    instance = await async_widget_instance_manager.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Widget instance not found")

    return {"instance": instance}


@router.put("/instances/{instance_id}")
async def admin_update_widget_instance(
    instance_id: str, request: WidgetInstanceUpdateRequest, user: User = Depends(get_current_user)
):
    """Update a widget instance"""
    existing = await async_widget_instance_manager.get_instance(instance_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Widget instance not found")

    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}

    instance = await async_widget_instance_manager.update_instance(instance_id, **kwargs)

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
async def admin_delete_widget_instance(instance_id: str, user: User = Depends(get_current_user)):
    """Delete a widget instance"""
    success = await async_widget_instance_manager.delete_instance(instance_id)
    if not success:
        raise HTTPException(status_code=404, detail="Widget instance not found")

    # Audit log
    await async_audit_logger.log(
        action="delete", resource="widget_instance", resource_id=instance_id, user_id=user.username
    )

    return {"status": "ok", "message": f"Widget instance {instance_id} deleted"}
