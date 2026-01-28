# app/routers/telegram.py
"""Telegram bot router - legacy config, instances CRUD, bot control."""

import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth_manager import User, get_current_user
from db.integration import (
    async_audit_logger,
    async_bot_instance_manager,
    async_config_manager,
    async_telegram_manager,
)
from multi_bot_manager import multi_bot_manager


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/telegram", tags=["telegram"])

# Telegram bot process management (legacy single-bot)
_telegram_bot_process = None


# ============== Pydantic Models ==============


class AdminTelegramConfigRequest(BaseModel):
    enabled: bool = False
    bot_token: Optional[str] = None
    api_url: str = "http://localhost:8002"
    allowed_users: List[int] = []
    admin_users: List[int] = []
    welcome_message: str = ""
    unauthorized_message: str = ""
    error_message: str = ""
    typing_enabled: bool = True


class BotInstanceCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    enabled: bool = True
    bot_token: Optional[str] = None
    allowed_users: List[int] = []
    admin_users: List[int] = []
    welcome_message: str = "Здравствуйте! Я AI-ассистент. Чем могу помочь?"
    unauthorized_message: str = "Извините, у вас нет доступа к этому боту."
    error_message: str = "Произошла ошибка. Попробуйте позже."
    typing_enabled: bool = True
    llm_backend: str = "vllm"
    llm_persona: str = "gulya"
    system_prompt: Optional[str] = None
    llm_params: Optional[dict] = None
    tts_engine: str = "xtts"
    tts_voice: str = "gulya"
    tts_preset: Optional[str] = None


class BotInstanceUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    bot_token: Optional[str] = None
    allowed_users: Optional[List[int]] = None
    admin_users: Optional[List[int]] = None
    welcome_message: Optional[str] = None
    unauthorized_message: Optional[str] = None
    error_message: Optional[str] = None
    typing_enabled: Optional[bool] = None
    llm_backend: Optional[str] = None
    llm_persona: Optional[str] = None
    system_prompt: Optional[str] = None
    llm_params: Optional[dict] = None
    tts_engine: Optional[str] = None
    tts_voice: Optional[str] = None
    tts_preset: Optional[str] = None


# ============== Legacy Config Endpoints ==============


@router.get("/config")
async def admin_get_telegram_config():
    """Получить конфигурацию Telegram бота (legacy endpoint - uses 'default' instance)"""
    # Try to get from default bot instance first (with token for internal use)
    instance = await async_bot_instance_manager.get_instance_with_token("default")
    if instance:
        # Convert instance format to legacy config format
        config = {
            "enabled": instance.get("enabled", False),
            "bot_token": instance.get("bot_token", ""),
            "api_url": f"http://localhost:{os.getenv('ORCHESTRATOR_PORT', '8002')}",
            "allowed_users": instance.get("allowed_users", []),
            "admin_users": instance.get("admin_users", []),
            "welcome_message": instance.get("welcome_message", ""),
            "unauthorized_message": instance.get("unauthorized_message", ""),
            "error_message": instance.get("error_message", ""),
            "typing_enabled": instance.get("typing_enabled", True),
        }
    else:
        # Fallback to legacy config
        config = await async_config_manager.get_telegram()

    # Маскируем токен для безопасности
    if config.get("bot_token"):
        token = config["bot_token"]
        if len(token) > 10:
            config["bot_token_masked"] = token[:4] + "..." + token[-4:]
        else:
            config["bot_token_masked"] = "***"
    else:
        config["bot_token_masked"] = ""
    return {"config": config}


@router.post("/config")
async def admin_save_telegram_config(
    request: AdminTelegramConfigRequest, user: User = Depends(get_current_user)
):
    """Сохранить конфигурацию Telegram бота (legacy endpoint - saves to 'default' instance)"""
    # Load existing to preserve token if not provided
    existing_instance = await async_bot_instance_manager.get_instance_with_token("default")
    existing_legacy = await async_config_manager.get_telegram()

    # Use token from instance first, then legacy, then request
    existing_token = ""
    if existing_instance and existing_instance.get("bot_token"):
        existing_token = existing_instance["bot_token"]
    elif existing_legacy.get("bot_token"):
        existing_token = existing_legacy["bot_token"]

    config = {
        "enabled": request.enabled,
        "bot_token": request.bot_token if request.bot_token else existing_token,
        "api_url": request.api_url,
        "allowed_users": request.allowed_users,
        "admin_users": request.admin_users,
        "welcome_message": request.welcome_message,
        "unauthorized_message": request.unauthorized_message,
        "error_message": request.error_message,
        "typing_enabled": request.typing_enabled,
    }

    # Save to legacy config (backward compatibility)
    await async_config_manager.set_telegram(config)

    # Also save to 'default' bot instance
    instance_data = {
        "enabled": config["enabled"],
        "bot_token": config["bot_token"],
        "allowed_users": config["allowed_users"],
        "admin_users": config["admin_users"],
        "welcome_message": config["welcome_message"],
        "unauthorized_message": config["unauthorized_message"],
        "error_message": config["error_message"],
        "typing_enabled": config["typing_enabled"],
    }

    if existing_instance:
        await async_bot_instance_manager.update_instance("default", **instance_data)
    else:
        # Create default instance if it doesn't exist
        await async_bot_instance_manager.create_instance(
            name="Default Bot",
            description="Default Telegram bot (legacy)",
            id="default",
            **instance_data,
        )

    # Audit log
    await async_audit_logger.log(
        action="update",
        resource="config",
        resource_id="telegram",
        user_id=user.username,
        details={"enabled": config["enabled"]},
    )

    return {"status": "ok", "config": config}


@router.get("/status")
async def admin_get_telegram_status():
    """Получить статус Telegram бота (legacy endpoint - uses 'default' instance)"""
    global _telegram_bot_process

    # Try to get config from default instance first
    instance = await async_bot_instance_manager.get_instance_with_token("default")
    if instance:
        config = instance
    else:
        config = await async_config_manager.get_telegram()

    running = False

    if _telegram_bot_process is not None:
        if _telegram_bot_process.poll() is None:
            running = True
        else:
            _telegram_bot_process = None

    # Count sessions from database (for default bot)
    sessions = await async_telegram_manager.get_sessions_for_bot("default")
    sessions_count = len(sessions)

    return {
        "status": {
            "running": running,
            "enabled": config.get("enabled", False),
            "has_token": bool(config.get("bot_token")),
            "active_sessions": sessions_count,
            "allowed_users_count": len(config.get("allowed_users", [])),
            "admin_users_count": len(config.get("admin_users", [])),
            "pid": _telegram_bot_process.pid if _telegram_bot_process else None,
        }
    }


@router.post("/start")
async def admin_start_telegram_bot():
    """Запустить Telegram бота"""
    global _telegram_bot_process

    config = await async_config_manager.get_telegram()

    if not config.get("bot_token"):
        raise HTTPException(status_code=400, detail="Bot token not configured")

    if not config.get("enabled"):
        raise HTTPException(status_code=400, detail="Bot is disabled in config")

    # Check if already running
    if _telegram_bot_process is not None and _telegram_bot_process.poll() is None:
        return {"status": "already_running", "pid": _telegram_bot_process.pid}

    # Start bot process
    # Get project root (parent of app directory)
    project_root = Path(__file__).parent.parent.parent
    bot_script = project_root / "telegram_bot_service.py"
    bot_log = project_root / "logs" / "telegram_bot.log"

    # Ensure logs directory exists
    bot_log.parent.mkdir(exist_ok=True)

    if not bot_script.exists():
        raise HTTPException(status_code=500, detail="Bot script not found")

    try:
        # Open log file for bot output
        log_file = open(bot_log, "a", encoding="utf-8")
        _telegram_bot_process = subprocess.Popen(
            ["python3", "-u", str(bot_script)],  # -u for unbuffered output
            cwd=str(project_root),
            stdout=log_file,
            stderr=subprocess.STDOUT,  # Redirect stderr to stdout (both to log file)
            start_new_session=True,  # Detach from parent process group
        )
        logger.info(f"Started Telegram bot with PID {_telegram_bot_process.pid}, logs: {bot_log}")
        return {"status": "started", "pid": _telegram_bot_process.pid}
    except Exception as e:
        logger.error(f"Failed to start Telegram bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def admin_stop_telegram_bot():
    """Остановить Telegram бота"""
    global _telegram_bot_process

    if _telegram_bot_process is None:
        return {"status": "not_running"}

    if _telegram_bot_process.poll() is not None:
        _telegram_bot_process = None
        return {"status": "not_running"}

    try:
        _telegram_bot_process.terminate()
        _telegram_bot_process.wait(timeout=5)
        logger.info("Telegram bot stopped")
    except Exception as e:
        logger.error(f"Error stopping bot: {e}")
        _telegram_bot_process.kill()

    _telegram_bot_process = None
    return {"status": "stopped"}


@router.post("/restart")
async def admin_restart_telegram_bot():
    """Перезапустить Telegram бота"""
    await admin_stop_telegram_bot()
    await asyncio.sleep(1)
    return await admin_start_telegram_bot()


@router.delete("/sessions")
async def admin_clear_telegram_sessions():
    """Очистить все сессии Telegram"""
    count = await async_telegram_manager.clear_all()
    return {"status": "ok", "message": f"Cleared {count} sessions"}


@router.get("/sessions")
async def admin_get_telegram_sessions():
    """Получить список сессий Telegram (legacy, for default bot)"""
    sessions = await async_telegram_manager.get_sessions_dict()
    return {"sessions": sessions}


# ============== Bot Instances Endpoints ==============


@router.get("/instances")
async def admin_list_bot_instances(enabled_only: bool = False):
    """List all Telegram bot instances"""
    instances = await async_bot_instance_manager.list_instances(enabled_only=enabled_only)

    # Add running status from multi_bot_manager
    statuses = await multi_bot_manager.get_all_statuses()
    for instance in instances:
        instance["running"] = statuses.get(instance["id"], {}).get("running", False)

    return {"instances": instances}


@router.post("/instances")
async def admin_create_bot_instance(
    request: BotInstanceCreateRequest, user: User = Depends(get_current_user)
):
    """Create a new Telegram bot instance"""
    # Convert request to dict, removing None values
    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}

    instance = await async_bot_instance_manager.create_instance(**kwargs)

    # Audit log
    await async_audit_logger.log(
        action="create",
        resource="bot_instance",
        resource_id=instance["id"],
        user_id=user.username,
        details={"name": instance["name"]},
    )

    return {"instance": instance}


@router.get("/instances/{instance_id}")
async def admin_get_bot_instance(instance_id: str, include_token: bool = False):
    """Get a specific bot instance"""
    if include_token:
        instance = await async_bot_instance_manager.get_instance_with_token(instance_id)
    else:
        instance = await async_bot_instance_manager.get_instance(instance_id)

    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    # Add running status
    status = await multi_bot_manager.get_bot_status(instance_id)
    instance["running"] = status.get("running", False)
    instance["pid"] = status.get("pid")

    return {"instance": instance}


@router.put("/instances/{instance_id}")
async def admin_update_bot_instance(
    instance_id: str, request: BotInstanceUpdateRequest, user: User = Depends(get_current_user)
):
    """Update a bot instance"""
    # Check if exists
    existing = await async_bot_instance_manager.get_instance(instance_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    # Convert request to dict, removing None values
    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}

    instance = await async_bot_instance_manager.update_instance(instance_id, **kwargs)

    # Audit log
    await async_audit_logger.log(
        action="update",
        resource="bot_instance",
        resource_id=instance_id,
        user_id=user.username,
        details={"name": instance.get("name")},
    )

    return {"instance": instance}


@router.delete("/instances/{instance_id}")
async def admin_delete_bot_instance(instance_id: str, user: User = Depends(get_current_user)):
    """Delete a bot instance"""
    # Stop bot if running
    await multi_bot_manager.stop_bot(instance_id)

    success = await async_bot_instance_manager.delete_instance(instance_id)
    if not success:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    # Audit log
    await async_audit_logger.log(
        action="delete", resource="bot_instance", resource_id=instance_id, user_id=user.username
    )

    return {"status": "ok", "message": f"Bot instance {instance_id} deleted"}


@router.post("/instances/{instance_id}/start")
async def admin_start_bot_instance(instance_id: str):
    """Start a specific bot instance"""
    # Check if instance exists
    instance = await async_bot_instance_manager.get_instance_with_token(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    if not instance.get("bot_token"):
        raise HTTPException(status_code=400, detail="Bot token not configured")

    if not instance.get("enabled"):
        raise HTTPException(status_code=400, detail="Bot instance is disabled")

    result = await multi_bot_manager.start_bot(instance_id)
    return result


@router.post("/instances/{instance_id}/stop")
async def admin_stop_bot_instance(instance_id: str):
    """Stop a specific bot instance"""
    result = await multi_bot_manager.stop_bot(instance_id)
    return result


@router.post("/instances/{instance_id}/restart")
async def admin_restart_bot_instance(instance_id: str):
    """Restart a specific bot instance"""
    result = await multi_bot_manager.restart_bot(instance_id)
    return result


@router.get("/instances/{instance_id}/status")
async def admin_get_bot_instance_status(instance_id: str):
    """Get status of a specific bot instance"""
    instance = await async_bot_instance_manager.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    status = await multi_bot_manager.get_bot_status(instance_id)

    # Add session count
    sessions = await async_telegram_manager.get_sessions_for_bot(instance_id)

    return {
        "status": {
            **status,
            "enabled": instance.get("enabled", False),
            "has_token": bool(instance.get("bot_token_masked")),
            "active_sessions": len(sessions),
        }
    }


@router.get("/instances/{instance_id}/sessions")
async def admin_get_bot_instance_sessions(instance_id: str):
    """Get sessions for a specific bot instance"""
    sessions = await async_telegram_manager.get_sessions_for_bot(instance_id)
    return {"sessions": sessions}


@router.post("/instances/{instance_id}/sessions")
async def admin_create_bot_instance_session(instance_id: str, request: dict):
    """Create/register a session for a bot instance (used by telegram_bot_service)"""
    user_id = request.get("user_id")
    chat_session_id = request.get("chat_session_id")

    if not user_id or not chat_session_id:
        raise HTTPException(status_code=400, detail="user_id and chat_session_id required")

    await async_telegram_manager.set_session(
        user_id=user_id,
        chat_session_id=chat_session_id,
        username=request.get("username"),
        first_name=request.get("first_name"),
        last_name=request.get("last_name"),
        bot_id=instance_id,
    )

    return {"status": "ok"}


@router.delete("/instances/{instance_id}/sessions")
async def admin_clear_bot_instance_sessions(instance_id: str):
    """Clear all sessions for a specific bot instance"""
    count = await async_telegram_manager.clear_sessions_for_bot(instance_id)
    return {"status": "ok", "message": f"Cleared {count} sessions"}


@router.get("/instances/{instance_id}/logs")
async def admin_get_bot_instance_logs(instance_id: str, lines: int = 100):
    """Get recent logs for a bot instance"""
    logs = await multi_bot_manager.get_recent_logs(instance_id, lines)
    return {"logs": logs}
