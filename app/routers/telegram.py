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

from auth_manager import User, get_current_user, require_not_guest
from db.integration import (
    async_audit_logger,
    async_bot_instance_manager,
    async_config_manager,
    async_payment_manager,
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
    # YooMoney OAuth2
    yoomoney_client_id: Optional[str] = None
    yoomoney_client_secret: Optional[str] = None
    yoomoney_redirect_uri: Optional[str] = None
    # Rate limiting
    rate_limit_count: Optional[int] = None
    rate_limit_hours: Optional[int] = None


# ============== Legacy Config Endpoints ==============


@router.get("/config")
async def admin_get_telegram_config(user: User = Depends(get_current_user)):
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
    request: AdminTelegramConfigRequest, user: User = Depends(require_not_guest)
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
async def admin_get_telegram_status(user: User = Depends(get_current_user)):
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
async def admin_start_telegram_bot(user: User = Depends(require_not_guest)):
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
async def admin_stop_telegram_bot(user: User = Depends(require_not_guest)):
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
async def admin_restart_telegram_bot(user: User = Depends(require_not_guest)):
    """Перезапустить Telegram бота"""
    await admin_stop_telegram_bot()
    await asyncio.sleep(1)
    return await admin_start_telegram_bot()


@router.delete("/sessions")
async def admin_clear_telegram_sessions(user: User = Depends(require_not_guest)):
    """Очистить все сессии Telegram"""
    count = await async_telegram_manager.clear_all()
    return {"status": "ok", "message": f"Cleared {count} sessions"}


@router.get("/sessions")
async def admin_get_telegram_sessions(user: User = Depends(get_current_user)):
    """Получить список сессий Telegram (legacy, for default bot)"""
    sessions = await async_telegram_manager.get_sessions_dict()
    return {"sessions": sessions}


# ============== Bot Instances Endpoints ==============


@router.get("/instances")
async def admin_list_bot_instances(
    enabled_only: bool = False, user: User = Depends(get_current_user)
):
    """List all Telegram bot instances"""
    owner_id = None if user.role == "admin" else user.id
    instances = await async_bot_instance_manager.list_instances(
        enabled_only=enabled_only, owner_id=owner_id
    )

    # Add running status from multi_bot_manager
    statuses = await multi_bot_manager.get_all_statuses()
    for instance in instances:
        instance["running"] = statuses.get(instance["id"], {}).get("running", False)

    return {"instances": instances}


@router.post("/instances")
async def admin_create_bot_instance(
    request: BotInstanceCreateRequest, user: User = Depends(require_not_guest)
):
    """Create a new Telegram bot instance"""
    owner_id = None if user.role == "admin" else user.id
    # Convert request to dict, removing None values
    kwargs = {k: v for k, v in request.model_dump().items() if v is not None}
    kwargs["owner_id"] = owner_id

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
async def admin_get_bot_instance(
    instance_id: str, include_token: bool = False, user: User = Depends(get_current_user)
):
    """Get a specific bot instance"""
    owner_id = None if user.role == "admin" else user.id
    if include_token:
        instance = await async_bot_instance_manager.get_instance_with_token(instance_id)
    else:
        instance = await async_bot_instance_manager.get_instance(instance_id, owner_id=owner_id)

    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    # Add running status
    status = await multi_bot_manager.get_bot_status(instance_id)
    instance["running"] = status.get("running", False)
    instance["pid"] = status.get("pid")

    return {"instance": instance}


@router.put("/instances/{instance_id}")
async def admin_update_bot_instance(
    instance_id: str, request: BotInstanceUpdateRequest, user: User = Depends(require_not_guest)
):
    """Update a bot instance"""
    # Check if exists and verify ownership
    owner_id = None if user.role == "admin" else user.id
    existing = await async_bot_instance_manager.get_instance(instance_id, owner_id=owner_id)
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
async def admin_delete_bot_instance(instance_id: str, user: User = Depends(require_not_guest)):
    """Delete a bot instance"""
    owner_id = None if user.role == "admin" else user.id
    # Stop bot if running
    await multi_bot_manager.stop_bot(instance_id)

    success = await async_bot_instance_manager.delete_instance(instance_id, owner_id=owner_id)
    if not success:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    # Audit log
    await async_audit_logger.log(
        action="delete", resource="bot_instance", resource_id=instance_id, user_id=user.username
    )

    return {"status": "ok", "message": f"Bot instance {instance_id} deleted"}


@router.post("/instances/{instance_id}/start")
async def admin_start_bot_instance(instance_id: str, user: User = Depends(require_not_guest)):
    """Start a specific bot instance and enable auto-start"""
    # Check if instance exists
    instance = await async_bot_instance_manager.get_instance_with_token(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    if not instance.get("bot_token"):
        raise HTTPException(status_code=400, detail="Bot token not configured")

    if not instance.get("enabled"):
        raise HTTPException(status_code=400, detail="Bot instance is disabled")

    result = await multi_bot_manager.start_bot(instance_id)

    # Save auto_start=True so bot restarts on app launch
    if result.get("status") in ["started", "already_running"]:
        await async_bot_instance_manager.set_auto_start(instance_id, True)

    return result


@router.post("/instances/{instance_id}/stop")
async def admin_stop_bot_instance(instance_id: str, user: User = Depends(require_not_guest)):
    """Stop a specific bot instance and disable auto-start"""
    result = await multi_bot_manager.stop_bot(instance_id)

    # Save auto_start=False so bot doesn't restart on app launch
    if result.get("status") == "stopped":
        await async_bot_instance_manager.set_auto_start(instance_id, False)

    return result


@router.post("/instances/{instance_id}/restart")
async def admin_restart_bot_instance(instance_id: str, user: User = Depends(require_not_guest)):
    """Restart a specific bot instance"""
    result = await multi_bot_manager.restart_bot(instance_id)
    return result


@router.get("/instances/{instance_id}/status")
async def admin_get_bot_instance_status(instance_id: str, user: User = Depends(get_current_user)):
    """Get status of a specific bot instance"""
    owner_id = None if user.role == "admin" else user.id
    instance = await async_bot_instance_manager.get_instance(instance_id, owner_id=owner_id)
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
async def admin_get_bot_instance_sessions(instance_id: str, user: User = Depends(get_current_user)):
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
async def admin_clear_bot_instance_sessions(
    instance_id: str, user: User = Depends(require_not_guest)
):
    """Clear all sessions for a specific bot instance"""
    count = await async_telegram_manager.clear_sessions_for_bot(instance_id)
    return {"status": "ok", "message": f"Cleared {count} sessions"}


@router.get("/instances/{instance_id}/logs")
async def admin_get_bot_instance_logs(
    instance_id: str, lines: int = 100, user: User = Depends(get_current_user)
):
    """Get recent logs for a bot instance"""
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
    instance = await async_bot_instance_manager.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    payment = await async_payment_manager.log_payment(
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
    instance = await async_bot_instance_manager.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    payments = await async_payment_manager.get_payments_for_bot(instance_id, limit)
    return {"payments": payments}


@router.get("/instances/{instance_id}/payments/stats")
async def admin_get_payment_stats(instance_id: str):
    """Get payment statistics for a bot instance."""
    instance = await async_bot_instance_manager.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    stats = await async_payment_manager.get_payment_stats(instance_id)
    return {"stats": stats}


# ============== YooMoney OAuth2 Endpoints ==============


@router.get("/instances/{instance_id}/yoomoney/auth-url")
async def admin_yoomoney_auth_url(instance_id: str, user: User = Depends(get_current_user)):
    """Generate YooMoney OAuth2 authorization URL."""
    from app.services.yoomoney_service import build_auth_url

    instance = await async_bot_instance_manager.get_instance_with_token(instance_id)
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

    instance = await async_bot_instance_manager.get_instance_with_token(instance_id)
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
    await async_bot_instance_manager.update_instance(
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
async def admin_yoomoney_status(instance_id: str, user: User = Depends(get_current_user)):
    """Check YooMoney connection status and wallet balance."""
    from app.services.yoomoney_service import get_account_info

    instance = await async_bot_instance_manager.get_instance_with_token(instance_id)
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
async def admin_yoomoney_disconnect(instance_id: str, user: User = Depends(get_current_user)):
    """Disconnect YooMoney — remove access token."""
    instance = await async_bot_instance_manager.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Bot instance not found")

    await async_bot_instance_manager.update_instance(
        instance_id,
        yoomoney_access_token=None,
        yoomoney_wallet_id=None,
    )
    return {"status": "disconnected"}
