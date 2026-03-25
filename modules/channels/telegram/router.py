# modules/channels/telegram/router.py
"""Telegram bot router - legacy config, instances CRUD, bot control."""

import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth_manager import User, require_permission, user_has_level, workspace_context
from modules.admin.service import resource_share_service
from modules.channels.telegram.service import bot_instance_service, telegram_session_service
from modules.core.service import config_service
from modules.monitoring.service import audit_service, payment_service
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
    llm_persona: str = "anna"
    system_prompt: Optional[str] = None
    llm_params: Optional[dict] = None
    tts_engine: str = "xtts"
    tts_voice: str = "anna"
    tts_preset: Optional[str] = None
    action_buttons: Optional[List[dict]] = None
    payment_enabled: bool = False
    yookassa_provider_token: Optional[str] = None
    stars_enabled: bool = False
    payment_products: Optional[list] = None
    payment_success_message: Optional[str] = None
    # Sales funnel
    sales_funnel_enabled: bool = True
    # RAG
    rag_mode: str = "all"
    knowledge_collection_ids: Optional[List[int]] = None
    # YooMoney OAuth2
    yoomoney_client_id: Optional[str] = None
    yoomoney_client_secret: Optional[str] = None
    yoomoney_redirect_uri: Optional[str] = None


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
    action_buttons: Optional[List[dict]] = None
    payment_enabled: Optional[bool] = None
    yookassa_provider_token: Optional[str] = None
    stars_enabled: Optional[bool] = None
    payment_products: Optional[list] = None
    payment_success_message: Optional[str] = None
    # Sales funnel
    sales_funnel_enabled: Optional[bool] = None
    # RAG
    rag_mode: Optional[str] = None
    knowledge_collection_ids: Optional[List[int]] = None
    # YooMoney OAuth2
    yoomoney_client_id: Optional[str] = None
    yoomoney_client_secret: Optional[str] = None
    yoomoney_redirect_uri: Optional[str] = None
    # Rate limiting
    rate_limit_count: Optional[int] = None
    rate_limit_hours: Optional[int] = None


class InstanceShareRequest(BaseModel):
    user_id: int
    permission: str = "view"  # "view" or "edit"


class InstanceUpdateShareRequest(BaseModel):
    permission: str  # "view" or "edit"


RESOURCE_TYPE_BOT = "bot_instance"


async def _check_instance_owner_or_admin(
    instance_id: str, user: User, resource_type: str = RESOURCE_TYPE_BOT
) -> dict:
    """Verify user is owner or admin of the instance. Returns instance dict."""
    owner_id, ws_id = workspace_context(user, "channels")
    instance = await bot_instance_service.get_instance(
        instance_id, owner_id=owner_id, workspace_id=ws_id
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")
    is_admin = user_has_level(user, "channels", "manage")
    is_owner = instance.get("owner_id") == user.id
    if not is_admin and not is_owner:
        raise HTTPException(status_code=403, detail="Only owner or admin can manage shares")
    return instance


async def _check_share_edit_permission(
    instance_id: str, user: User, resource_type: str = RESOURCE_TYPE_BOT
) -> None:
    """Check if shared user has edit permission. Raises 403 if view-only."""
    is_admin = user_has_level(user, "channels", "manage")
    if is_admin:
        return
    perm = await resource_share_service.get_user_permission(resource_type, instance_id, user.id)
    if perm == "view":
        raise HTTPException(status_code=403, detail="View-only access — editing not allowed")


# ============== Legacy Config Endpoints ==============


@router.get("/config")
async def admin_get_telegram_config(user: User = Depends(require_permission("channels", "view"))):
    """Получить конфигурацию Telegram бота (legacy endpoint - uses 'default' instance)"""
    # Try to get from default bot instance first (with token for internal use)
    instance = await bot_instance_service.get_instance_with_token("default")
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
        config = await config_service.get_telegram()

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
    request: AdminTelegramConfigRequest,
    user: User = Depends(require_permission("channels", "edit")),
):
    """Сохранить конфигурацию Telegram бота (legacy endpoint - saves to 'default' instance)"""
    # Load existing to preserve token if not provided
    existing_instance = await bot_instance_service.get_instance_with_token("default")
    existing_legacy = await config_service.get_telegram()

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
    await config_service.set_telegram(config)

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
        await bot_instance_service.update_instance("default", **instance_data)
    else:
        # Create default instance if it doesn't exist
        await bot_instance_service.create_instance(
            name="Default Bot",
            description="Default Telegram bot (legacy)",
            id="default",
            **instance_data,
        )

    # Audit log
    await audit_service.log(
        action="update",
        resource="config",
        resource_id="telegram",
        user_id=user.username,
        details={"enabled": config["enabled"]},
    )

    return {"status": "ok", "config": config}


@router.get("/status")
async def admin_get_telegram_status(user: User = Depends(require_permission("channels", "view"))):
    """Получить статус Telegram бота (legacy endpoint - uses 'default' instance)"""
    global _telegram_bot_process

    # Try to get config from default instance first
    instance = await bot_instance_service.get_instance_with_token("default")
    if instance:
        config = instance
    else:
        config = await config_service.get_telegram()

    running = False

    if _telegram_bot_process is not None:
        if _telegram_bot_process.poll() is None:
            running = True
        else:
            _telegram_bot_process = None

    # Count sessions from database (for default bot)
    sessions = await telegram_session_service.get_sessions_for_bot("default")
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
async def admin_start_telegram_bot(user: User = Depends(require_permission("channels", "edit"))):
    """Запустить Telegram бота"""
    global _telegram_bot_process

    config = await config_service.get_telegram()

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
async def admin_stop_telegram_bot(user: User = Depends(require_permission("channels", "edit"))):
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
async def admin_restart_telegram_bot(user: User = Depends(require_permission("channels", "edit"))):
    """Перезапустить Telegram бота"""
    await admin_stop_telegram_bot()
    await asyncio.sleep(1)
    return await admin_start_telegram_bot()


@router.delete("/sessions")
async def admin_clear_telegram_sessions(
    user: User = Depends(require_permission("channels", "edit")),
):
    """Очистить все сессии Telegram"""
    count = await telegram_session_service.clear_all()
    return {"status": "ok", "message": f"Cleared {count} sessions"}


@router.get("/sessions")
async def admin_get_telegram_sessions(user: User = Depends(require_permission("channels", "view"))):
    """Получить список сессий Telegram (legacy, for default bot)"""
    sessions = await telegram_session_service.get_sessions_dict()
    return {"sessions": sessions}


# ============== Bot Instances Endpoints ==============


@router.get("/instances")
async def admin_list_bot_instances(
    enabled_only: bool = False, user: User = Depends(require_permission("channels", "view"))
):
    """List all Telegram bot instances"""
    owner_id, ws_id = workspace_context(user, "channels")
    instances = await bot_instance_service.list_instances(
        enabled_only=enabled_only, owner_id=owner_id, workspace_id=ws_id
    )

    # Add running status from multi_bot_manager
    statuses = await multi_bot_manager.get_all_statuses()
    for instance in instances:
        instance["running"] = statuses.get(instance["id"], {}).get("running", False)

    # Enrich with share info
    instance_ids = [i["id"] for i in instances]
    share_counts = await resource_share_service.get_share_counts(RESOURCE_TYPE_BOT, instance_ids)
    shared_with_me = {}
    if owner_id is not None:
        shared_with_me = await resource_share_service.get_shared_resources_with_permissions(
            RESOURCE_TYPE_BOT, owner_id
        )
    for instance in instances:
        iid = instance["id"]
        instance["share_count"] = share_counts.get(iid, 0)
        instance["is_shared_with_me"] = iid in shared_with_me
        instance["share_permission"] = shared_with_me.get(iid)

    return {"instances": instances}


@router.post("/instances")
async def admin_create_bot_instance(
    request: BotInstanceCreateRequest, user: User = Depends(require_permission("channels", "edit"))
):
    """Create a new Telegram bot instance"""
    owner_id, ws_id = workspace_context(user, "channels")
    # Convert request to dict, removing None values
    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}
    kwargs["owner_id"] = owner_id
    kwargs["workspace_id"] = ws_id

    instance = await bot_instance_service.create_instance(**kwargs)

    # Audit log
    await audit_service.log(
        action="create",
        resource="bot_instance",
        resource_id=instance["id"],
        user_id=user.username,
        details={"name": instance["name"]},
    )

    return {"instance": instance}


@router.get("/instances/{instance_id}")
async def admin_get_bot_instance(
    instance_id: str,
    include_token: bool = False,
    user: User = Depends(require_permission("channels", "view")),
):
    """Get a specific bot instance"""
    owner_id, ws_id = workspace_context(user, "channels")
    if include_token:
        instance = await bot_instance_service.get_instance_with_token(instance_id)
    else:
        instance = await bot_instance_service.get_instance(
            instance_id, owner_id=owner_id, workspace_id=ws_id
        )

    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    # Add running status
    status = await multi_bot_manager.get_bot_status(instance_id)
    instance["running"] = status.get("running", False)
    instance["pid"] = status.get("pid")

    return {"instance": instance}


@router.put("/instances/{instance_id}")
async def admin_update_bot_instance(
    instance_id: str,
    request: BotInstanceUpdateRequest,
    user: User = Depends(require_permission("channels", "edit")),
):
    """Update a bot instance"""
    # Check if exists and verify ownership
    owner_id, ws_id = workspace_context(user, "channels")
    existing = await bot_instance_service.get_instance(
        instance_id, owner_id=owner_id, workspace_id=ws_id
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    # Shared users need edit permission
    await _check_share_edit_permission(instance_id, user, RESOURCE_TYPE_BOT)

    # Convert request to dict, removing None values
    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}

    instance = await bot_instance_service.update_instance(instance_id, **kwargs)

    # Audit log
    await audit_service.log(
        action="update",
        resource="bot_instance",
        resource_id=instance_id,
        user_id=user.username,
        details={"name": instance.get("name")},
    )

    return {"instance": instance}


@router.delete("/instances/{instance_id}")
async def admin_delete_bot_instance(
    instance_id: str, user: User = Depends(require_permission("channels", "edit"))
):
    """Delete a bot instance — only owner or admin"""
    owner_id, ws_id = workspace_context(user, "channels")
    # Stop bot if running
    await multi_bot_manager.stop_bot(instance_id)

    success = await bot_instance_service.delete_instance(
        instance_id, owner_id=owner_id, workspace_id=ws_id
    )
    if not success:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    # Clean up shares
    await resource_share_service.remove_all_shares(RESOURCE_TYPE_BOT, instance_id)

    # Audit log
    await audit_service.log(
        action="delete", resource="bot_instance", resource_id=instance_id, user_id=user.username
    )

    return {"status": "ok", "message": f"Bot instance {instance_id} deleted"}


@router.post("/instances/{instance_id}/start")
async def admin_start_bot_instance(
    instance_id: str, user: User = Depends(require_permission("channels", "edit"))
):
    """Start a specific bot instance and enable auto-start"""
    # Workspace gate-check
    instance = await bot_instance_service.get_instance(instance_id, workspace_id=user.workspace_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    # Shared users need edit permission
    await _check_share_edit_permission(instance_id, user, RESOURCE_TYPE_BOT)

    # Re-fetch with token for start logic
    instance = await bot_instance_service.get_instance_with_token(instance_id)

    if not instance.get("bot_token"):
        raise HTTPException(status_code=400, detail="Bot token not configured")

    if not instance.get("enabled"):
        raise HTTPException(status_code=400, detail="Bot instance is disabled")

    result = await multi_bot_manager.start_bot(instance_id)

    # Save auto_start=True so bot restarts on app launch
    if result.get("status") in ["started", "already_running"]:
        await bot_instance_service.set_auto_start(instance_id, True)

    return result


@router.post("/instances/{instance_id}/stop")
async def admin_stop_bot_instance(
    instance_id: str, user: User = Depends(require_permission("channels", "edit"))
):
    """Stop a specific bot instance and disable auto-start"""
    # Workspace gate-check
    instance = await bot_instance_service.get_instance(instance_id, workspace_id=user.workspace_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    # Shared users need edit permission
    await _check_share_edit_permission(instance_id, user, RESOURCE_TYPE_BOT)

    result = await multi_bot_manager.stop_bot(instance_id)

    # Save auto_start=False so bot doesn't restart on app launch
    if result.get("status") == "stopped":
        await bot_instance_service.set_auto_start(instance_id, False)

    return result


@router.post("/instances/{instance_id}/restart")
async def admin_restart_bot_instance(
    instance_id: str, user: User = Depends(require_permission("channels", "edit"))
):
    """Restart a specific bot instance"""
    # Workspace gate-check
    instance = await bot_instance_service.get_instance(instance_id, workspace_id=user.workspace_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    # Shared users need edit permission
    await _check_share_edit_permission(instance_id, user, RESOURCE_TYPE_BOT)

    result = await multi_bot_manager.restart_bot(instance_id)
    return result


@router.get("/instances/{instance_id}/status")
async def admin_get_bot_instance_status(
    instance_id: str, user: User = Depends(require_permission("channels", "view"))
):
    """Get status of a specific bot instance"""
    owner_id, ws_id = workspace_context(user, "channels")
    instance = await bot_instance_service.get_instance(
        instance_id, owner_id=owner_id, workspace_id=ws_id
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    status = await multi_bot_manager.get_bot_status(instance_id)

    # Add session count
    sessions = await telegram_session_service.get_sessions_for_bot(instance_id)

    return {
        "status": {
            **status,
            "enabled": instance.get("enabled", False),
            "has_token": bool(instance.get("bot_token_masked")),
            "active_sessions": len(sessions),
        }
    }


@router.get("/instances/{instance_id}/sessions")
async def admin_get_bot_instance_sessions(
    instance_id: str, user: User = Depends(require_permission("channels", "view"))
):
    """Get sessions for a specific bot instance"""
    # Workspace gate-check
    instance = await bot_instance_service.get_instance(instance_id, workspace_id=user.workspace_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    sessions = await telegram_session_service.get_sessions_for_bot(instance_id)
    return {"sessions": sessions}


@router.post("/instances/{instance_id}/register-user")
async def register_bot_user(instance_id: str, request: dict):
    """Register a Telegram user for a bot instance (called by bot middleware, no auth)."""
    user_id = request.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")

    await telegram_session_service.register_user(
        user_id=user_id,
        bot_id=instance_id,
        username=request.get("username"),
        first_name=request.get("first_name"),
        last_name=request.get("last_name"),
    )

    return {"status": "ok"}


@router.post("/instances/{instance_id}/sessions")
async def admin_create_bot_instance_session(instance_id: str, request: dict):
    """Create/register a session for a bot instance (used by telegram_bot_service)"""
    user_id = request.get("user_id")
    chat_session_id = request.get("chat_session_id")

    if not user_id or not chat_session_id:
        raise HTTPException(status_code=400, detail="user_id and chat_session_id required")

    await telegram_session_service.set_session(
        user_id=user_id,
        chat_session_id=chat_session_id,
        username=request.get("username"),
        first_name=request.get("first_name"),
        last_name=request.get("last_name"),
        bot_id=instance_id,
    )

    return {"status": "ok"}


@router.delete("/instances/{instance_id}/sessions")
async def admin_clear_bot_instance_sessions(
    instance_id: str, user: User = Depends(require_permission("channels", "edit"))
):
    """Clear all sessions for a specific bot instance"""
    # Workspace gate-check
    instance = await bot_instance_service.get_instance(instance_id, workspace_id=user.workspace_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    count = await telegram_session_service.clear_sessions_for_bot(instance_id)
    return {"status": "ok", "message": f"Cleared {count} sessions"}


@router.get("/instances/{instance_id}/logs")
async def admin_get_bot_instance_logs(
    instance_id: str, lines: int = 100, user: User = Depends(require_permission("channels", "view"))
):
    """Get recent logs for a bot instance"""
    # Workspace gate-check
    instance = await bot_instance_service.get_instance(instance_id, workspace_id=user.workspace_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    logs = await multi_bot_manager.get_recent_logs(instance_id, lines)
    return {"logs": logs}


# ============== Payment Endpoints ==============


class PaymentLogRequest(BaseModel):
    user_id: int
    username: Optional[str] = None
    payment_type: str
    product_id: str
    amount: int
    currency: str
    telegram_payment_id: Optional[str] = None
    provider_payment_id: Optional[str] = None


@router.post("/instances/{instance_id}/payments")
async def admin_log_payment(instance_id: str, request: PaymentLogRequest):
    """Log a payment from telegram_bot_service (internal use)."""
    instance = await bot_instance_service.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    payment = await payment_service.log_payment(
        bot_id=instance_id,
        user_id=request.user_id,
        username=request.username,
        payment_type=request.payment_type,
        product_id=request.product_id,
        amount=request.amount,
        currency=request.currency,
        telegram_payment_id=request.telegram_payment_id,
        provider_payment_id=request.provider_payment_id,
    )

    return {"status": "ok", "payment": payment}


@router.get("/instances/{instance_id}/payments")
async def admin_get_payments(instance_id: str, limit: int = 100):
    """Get payment history for a bot instance."""
    instance = await bot_instance_service.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    payments = await payment_service.get_payments_for_bot(instance_id, limit)
    return {"payments": payments}


@router.get("/instances/{instance_id}/payments/stats")
async def admin_get_payment_stats(instance_id: str):
    """Get payment statistics for a bot instance."""
    instance = await bot_instance_service.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    stats = await payment_service.get_payment_stats(instance_id)
    return {"stats": stats}


# ============== YooMoney OAuth2 Endpoints ==============


@router.get("/instances/{instance_id}/yoomoney/auth-url")
async def admin_yoomoney_auth_url(
    instance_id: str, user: User = Depends(require_permission("channels", "view"))
):
    """Generate YooMoney OAuth2 authorization URL."""
    from app.services.yoomoney_service import build_auth_url

    instance = await bot_instance_service.get_instance_with_token(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    client_id = instance.get("yoomoney_client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="yoomoney_client_id not configured")

    redirect_uri = instance.get("yoomoney_redirect_uri")
    if not redirect_uri:
        # Default: current orchestrator URL + callback path
        port = os.getenv("ORCHESTRATOR_PORT", "8002")
        redirect_uri = (
            f"http://localhost:{port}/admin/telegram/instances/{instance_id}/yoomoney/callback"
        )

    url = build_auth_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        instance_name=instance.get("name", instance_id),
    )
    return {"auth_url": url, "redirect_uri": redirect_uri}


@router.get("/instances/{instance_id}/yoomoney/callback")
async def admin_yoomoney_callback(
    instance_id: str, code: Optional[str] = None, error: Optional[str] = None
):
    """Handle YooMoney OAuth2 callback — exchange code for access_token."""
    from app.services.yoomoney_service import exchange_code_for_token, get_account_info

    if error:
        return {"status": "error", "detail": f"YooMoney authorization denied: {error}"}

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    instance = await bot_instance_service.get_instance_with_token(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    client_id = instance.get("yoomoney_client_id", "")
    client_secret = instance.get("yoomoney_client_secret")
    redirect_uri = instance.get("yoomoney_redirect_uri", "")
    if not redirect_uri:
        port = os.getenv("ORCHESTRATOR_PORT", "8002")
        redirect_uri = (
            f"http://localhost:{port}/admin/telegram/instances/{instance_id}/yoomoney/callback"
        )

    # Exchange code for token
    result = exchange_code_for_token(
        code=code,
        client_id=client_id,
        redirect_uri=redirect_uri,
        client_secret=client_secret,
    )
    # Handle both sync and async
    if asyncio.iscoroutine(result):
        result = await result

    if "error" in result:
        return {"status": "error", "detail": result.get("error_description", result["error"])}

    access_token = result["access_token"]

    # Get wallet info
    account = await get_account_info(access_token)
    wallet_id = account.get("account", "") if account else ""

    # Save to database
    await bot_instance_service.update_instance(
        instance_id,
        yoomoney_access_token=access_token,
        yoomoney_wallet_id=wallet_id,
    )

    # Return HTML page that closes the popup
    from fastapi.responses import HTMLResponse

    return HTMLResponse(
        f"""<!DOCTYPE html><html><body>
        <h2>YooMoney подключён!</h2>
        <p>Кошелёк: {wallet_id}</p>
        <p>Это окно можно закрыть.</p>
        <script>
            if (window.opener) {{
                window.opener.postMessage({{type: 'yoomoney_connected', wallet_id: '{wallet_id}'}}, '*');
                setTimeout(() => window.close(), 2000);
            }}
        </script>
        </body></html>"""
    )


@router.get("/instances/{instance_id}/yoomoney/status")
async def admin_yoomoney_status(
    instance_id: str, user: User = Depends(require_permission("channels", "view"))
):
    """Check YooMoney connection status and wallet balance."""
    from app.services.yoomoney_service import get_account_info

    instance = await bot_instance_service.get_instance_with_token(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    access_token = instance.get("yoomoney_access_token")
    if not access_token:
        return {
            "connected": False,
            "client_id": instance.get("yoomoney_client_id"),
        }

    account = await get_account_info(access_token)
    if not account:
        return {"connected": False, "error": "Token expired or invalid"}

    return {
        "connected": True,
        "wallet_id": account.get("account"),
        "balance": account.get("balance"),
        "currency": account.get("currency", "RUB"),
        "account_type": account.get("account_type"),
    }


@router.post("/instances/{instance_id}/yoomoney/disconnect")
async def admin_yoomoney_disconnect(
    instance_id: str, user: User = Depends(require_permission("channels", "edit"))
):
    """Disconnect YooMoney — remove access token."""
    instance = await bot_instance_service.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    await bot_instance_service.update_instance(
        instance_id,
        yoomoney_access_token=None,
        yoomoney_wallet_id=None,
    )
    return {"status": "disconnected"}


# ============== Resource Sharing Endpoints ==============


@router.get("/shareable-users")
async def list_shareable_users(user: User = Depends(require_permission("channels", "view"))):
    """List users eligible for resource sharing."""
    users = await resource_share_service.list_shareable_users(exclude_user_id=user.id)
    return {"users": users}


@router.get("/instances/{instance_id}/shares")
async def get_instance_shares(
    instance_id: str, user: User = Depends(require_permission("channels", "view"))
):
    """List shares for a bot instance."""
    await _check_instance_owner_or_admin(instance_id, user)
    shares = await resource_share_service.get_shares(RESOURCE_TYPE_BOT, instance_id)
    return {"shares": shares}


@router.post("/instances/{instance_id}/shares")
async def add_instance_share(
    instance_id: str,
    request: InstanceShareRequest,
    user: User = Depends(require_permission("channels", "edit")),
):
    """Share a bot instance with another user."""
    await _check_instance_owner_or_admin(instance_id, user)

    if request.permission not in ("view", "edit"):
        raise HTTPException(status_code=400, detail="Permission must be 'view' or 'edit'")
    if request.user_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot share with yourself")

    share = await resource_share_service.add_share(
        RESOURCE_TYPE_BOT,
        instance_id,
        request.user_id,
        request.permission,
        shared_by=user.id,
    )

    await audit_service.log(
        action="share",
        resource="bot_instance",
        resource_id=instance_id,
        user_id=user.username,
        details={"shared_with": request.user_id, "permission": request.permission},
    )

    return {"share": share}


@router.put("/instances/{instance_id}/shares/{target_user_id}")
async def update_instance_share(
    instance_id: str,
    target_user_id: int,
    request: InstanceUpdateShareRequest,
    user: User = Depends(require_permission("channels", "edit")),
):
    """Update share permission for a bot instance."""
    await _check_instance_owner_or_admin(instance_id, user)

    if request.permission not in ("view", "edit"):
        raise HTTPException(status_code=400, detail="Permission must be 'view' or 'edit'")

    success = await resource_share_service.update_permission(
        RESOURCE_TYPE_BOT, instance_id, target_user_id, request.permission
    )
    if not success:
        raise HTTPException(status_code=404, detail="Share not found")

    return {"status": "ok"}


@router.delete("/instances/{instance_id}/shares/{target_user_id}")
async def remove_instance_share(
    instance_id: str,
    target_user_id: int,
    user: User = Depends(require_permission("channels", "edit")),
):
    """Remove a share from a bot instance."""
    await _check_instance_owner_or_admin(instance_id, user)

    success = await resource_share_service.remove_share(
        RESOURCE_TYPE_BOT, instance_id, target_user_id
    )
    if not success:
        raise HTTPException(status_code=404, detail="Share not found")

    await audit_service.log(
        action="unshare",
        resource="bot_instance",
        resource_id=instance_id,
        user_id=user.username,
        details={"removed_user": target_user_id},
    )

    return {"status": "ok"}
