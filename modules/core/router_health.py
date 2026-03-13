"""Core health and status endpoints.

Provides root endpoint, health check, and deployment mode query.
"""

import logging
import os
from datetime import datetime

from fastapi import APIRouter

from app.dependencies import get_container
from cloud_llm_service import CloudLLMService
from db.integration import get_database_status


logger = logging.getLogger(__name__)

router = APIRouter(tags=["core"])

DEPLOYMENT_MODE = os.getenv("DEPLOYMENT_MODE", "full").lower()
if DEPLOYMENT_MODE not in ("full", "cloud", "local"):
    DEPLOYMENT_MODE = "full"


@router.get("/")
async def root():
    """Проверка работоспособности"""
    return {
        "status": "ok",
        "service": "AI Secretary Orchestrator",
        "endpoints": {
            "health": "/health",
            "process_call": "/process_call (POST)",
            "tts": "/tts (POST)",
            "stt": "/stt (POST)",
            "chat": "/chat (POST)",
        },
    }


@router.get("/health")
async def health_check():
    """Проверка здоровья всех сервисов"""
    container = get_container()
    current_llm_service = container.llm_service

    # Определяем тип LLM сервиса
    llm_backend_type = "unknown"
    if current_llm_service:
        if isinstance(current_llm_service, CloudLLMService):
            ptype = getattr(current_llm_service, "provider_type", "cloud")
            llm_backend_type = f"cloud ({ptype}: {current_llm_service.model_name})"
        elif hasattr(current_llm_service, "api_url"):  # vLLM
            llm_backend_type = f"vllm ({current_llm_service.model_name})"
        elif hasattr(current_llm_service, "model_name"):
            llm_backend_type = f"cloud ({current_llm_service.model_name})"

    services_status = {
        "voice_clone_xtts_anna": container.anna_voice_service is not None,
        "voice_clone_xtts_marina": container.voice_service is not None,
        "voice_clone_openvoice": container.openvoice_service is not None,
        "piper_tts": container.piper_service is not None,
        "stt": container.stt_service is not None,
        "llm": current_llm_service is not None,
        "llm_backend": llm_backend_type,
        "streaming_tts": container.streaming_tts_manager is not None,
        "current_voice": container.current_voice_config,
    }

    # Для health check достаточно любой TTS + llm
    any_tts = (
        services_status["voice_clone_xtts_anna"]
        or services_status["voice_clone_xtts_marina"]
        or services_status["voice_clone_openvoice"]
        or services_status["piper_tts"]
    )
    # In cloud mode, TTS is not required for healthy status
    if DEPLOYMENT_MODE == "cloud":
        core_ok = services_status["llm"]
    else:
        core_ok = any_tts and services_status["llm"]

    # Get database status
    db_status = await get_database_status()

    result = {
        "status": "healthy" if core_ok else "degraded",
        "deployment_mode": DEPLOYMENT_MODE,
        "services": services_status,
        "database": db_status.get("database", {}),
        "timestamp": datetime.now().isoformat(),
    }

    # Добавляем статистику streaming TTS если доступен
    if container.streaming_tts_manager is not None:
        result["streaming_tts_stats"] = container.streaming_tts_manager.get_stats()

    # Internet monitor status
    im = getattr(container, "internet_monitor", None)
    if im is not None:
        st = im.state
        result["internet"] = {
            "status": st.status.value,
            "ping_ms": round(st.ping_ms, 1) if st.ping_ms else None,
            "current_llm_backend": st.current_llm_backend,
            "switch_count": st.switch_count,
            "last_check": st.last_check,
        }

    return result


@router.get("/admin/deployment-mode")
async def get_deployment_mode():
    """Return current deployment mode for frontend."""
    return {"mode": DEPLOYMENT_MODE}
