#!/usr/bin/env python3
"""
Главный оркестратор - координирует все сервисы
STT (Whisper) -> LLM (vLLM / Cloud) -> TTS (XTTS v2)
"""

import asyncio
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import soundfile as sf
import uvicorn
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from pydantic import BaseModel
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.cors_middleware import DynamicCORSMiddleware
from app.rate_limiter import limiter

# Modular routers
from app.routers import (
    amocrm,
    audit,
    auth,
    backup,
    bot_sales,
    chat,
    claude_code,
    faq,
    github_repos,
    github_webhook,
    gsm,
    kanban,
    legal,
    llm,
    mobile,
    monitor,
    roles,
    services,
    stt,
    telegram,
    tts,
    usage,
    whatsapp,
    widget,
    wiki_rag,
    woocommerce,
    workspace,
    yoomoney_webhook,
)
from app.security_headers import (
    SECURITY_HEADERS_ENABLED,
    SecurityHeadersMiddleware,
)
from auth_manager import (
    LoginRequest,
    LoginResponse,
    User,
    authenticate_user,
    create_session,
    get_auth_status,
    get_current_user,
    require_permission,
)

# Cloud LLM service for multi-provider support
from cloud_llm_service import PROVIDER_TYPES, CloudLLMService
from db.integration import (
    async_audit_logger,
    async_cloud_provider_manager,
    async_faq_manager,
    async_preset_manager,
    async_role_manager,
    async_user_manager,
    async_workspace_manager,
    get_database_status,
    init_database,
    shutdown_database,
)

# Database integration
from finetune_manager import get_finetune_manager
from model_manager import get_model_manager


# Multi-bot manager
try:
    from piper_tts_service import PiperTTSService

    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False
    PiperTTSService = None

from service_manager import get_service_manager


try:
    from stt_service import STTService

    STT_AVAILABLE = True
except ImportError:
    STT_AVAILABLE = False
    STTService = None

from system_monitor import get_system_monitor


try:
    from tts_finetune_manager import get_tts_finetune_manager

    TTS_FINETUNE_AVAILABLE = True
except ImportError:
    TTS_FINETUNE_AVAILABLE = False
    get_tts_finetune_manager = None

# Импорты наших сервисов
try:
    from voice_clone_service import VoiceCloneService

    XTTS_AVAILABLE = True
except ImportError:
    XTTS_AVAILABLE = False
    VoiceCloneService = None


# vLLM импорт (опциональный - локальная Llama через vLLM)
try:
    from vllm_llm_service import VLLMLLMService

    VLLM_AVAILABLE = True
except ImportError:
    VLLM_AVAILABLE = False
    VLLMLLMService = None

# OpenVoice импорт (опциональный - для GPU P104-100)
try:
    from openvoice_service import OpenVoiceService

    OPENVOICE_AVAILABLE = True
except ImportError:
    OPENVOICE_AVAILABLE = False
    OpenVoiceService = None

# Определяем какой LLM backend использовать
LLM_BACKEND = os.getenv("LLM_BACKEND", "vllm").lower()  # "vllm" or "cloud:{provider_id}"

# Deployment mode: "full" (default), "cloud" (no GPU/hardware), "local" (explicit full)
DEPLOYMENT_MODE = os.getenv("DEPLOYMENT_MODE", "full").lower()
if DEPLOYMENT_MODE not in ("full", "cloud", "local"):
    DEPLOYMENT_MODE = "full"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


from modules.speech.streaming import StreamingTTSManager  # noqa: E402


# Глобальный менеджер streaming TTS
streaming_tts_manager: Optional[StreamingTTSManager] = None

app = FastAPI(title="AI Secretary Orchestrator", version="1.0.0")

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS для доступа из браузера
# Static origins from env (comma-separated), default to "*" for development.
# Widget allowed_domains are added dynamically from the database.
CORS_ORIGINS_RAW = os.getenv("CORS_ORIGINS", "*")
CORS_ORIGINS = (
    ["*"]
    if CORS_ORIGINS_RAW == "*"
    else [origin.strip() for origin in CORS_ORIGINS_RAW.split(",") if origin.strip()]
)
app.add_middleware(DynamicCORSMiddleware, static_origins=CORS_ORIGINS)

# Security headers
app.add_middleware(SecurityHeadersMiddleware, enabled=SECURITY_HEADERS_ENABLED)

# Include modular routers
# NOTE: These routers use the ServiceContainer from app.dependencies
# which is populated in startup_event

# Always-available routers (all deployment modes)
app.include_router(auth.router)
app.include_router(audit.router)
app.include_router(faq.router)
app.include_router(llm.router)
app.include_router(chat.router)
app.include_router(telegram.router)
app.include_router(whatsapp.router)
app.include_router(usage.router)
app.include_router(widget.router)
app.include_router(mobile.router)
app.include_router(bot_sales.router)
app.include_router(github_webhook.router)
app.include_router(yoomoney_webhook.router)
app.include_router(legal.router)
app.include_router(backup.router)
app.include_router(wiki_rag.router)
app.include_router(amocrm.router)
app.include_router(amocrm.webhook_router)
app.include_router(woocommerce.router)
app.include_router(github_repos.router)
app.include_router(claude_code.router)
app.include_router(kanban.router)
app.include_router(roles.router)
app.include_router(workspace.router)

# Hardware/GPU routers — skip in cloud mode
if DEPLOYMENT_MODE != "cloud":
    app.include_router(services.router)
    app.include_router(monitor.router)
    app.include_router(gsm.router)
    if stt is not None:
        app.include_router(stt.router)
    if tts is not None:
        app.include_router(tts.router)

# Глобальные сервисы
voice_service: Optional["VoiceCloneService"] = None  # XTTS (Марина) - GPU CC >= 7.0
anna_voice_service: Optional["VoiceCloneService"] = None  # XTTS (Анна) - GPU CC >= 7.0
piper_service: Optional["PiperTTSService"] = None  # Piper (Dmitri, Irina) - CPU
openvoice_service: Optional["OpenVoiceService"] = None  # OpenVoice v2 (Марина) - GPU CC 6.1+
stt_service: Optional["STTService"] = None
llm_service = None  # VLLMLLMService or CloudLLMService instance

# Конфигурация текущего голоса
# engine: "xtts" (Марина/Анна на GPU CC>=7.0), "piper" (Dmitri/Irina на CPU), "openvoice" (Марина на GPU CC 6.1+)
# По умолчанию используем Гулю (XTTS) если доступна, иначе Piper
current_voice_config = {
    "engine": "xtts",
    "voice": "anna",  # anna / marina / dmitri / irina / marina_openvoice
}

# Папка для временных файлов
TEMP_DIR = Path("./temp")
TEMP_DIR.mkdir(exist_ok=True)

# Папка для логов звонков
CALLS_LOG_DIR = Path("./calls_log")
CALLS_LOG_DIR.mkdir(exist_ok=True)


async def _get_or_create_default_gemini_provider() -> Optional[dict]:
    """Find existing default Gemini provider or auto-create from GEMINI_API_KEY env.

    Returns provider config dict or None if no API key available.
    """
    # Try to find existing Gemini provider
    providers = await async_cloud_provider_manager.list_providers(enabled_only=False)
    for p in providers:
        if p.get("provider_type") == "gemini":
            return await async_cloud_provider_manager.get_provider_with_key(p["id"])

    # No Gemini provider exists — create one from env
    api_key = os.getenv("GEMINI_API_KEY", "")
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    if not api_key:
        logger.warning("GEMINI_API_KEY not set, cannot auto-create Gemini cloud provider")
        return None

    logger.info("Auto-creating default Gemini cloud provider from GEMINI_API_KEY...")
    provider = await async_cloud_provider_manager.create_provider(
        name="Gemini (Auto-created)",
        provider_type="gemini",
        api_key=api_key,
        model_name=model_name,
        enabled=True,
        is_default=True,
        description="Auto-created from GEMINI_API_KEY environment variable",
    )
    logger.info(f"Created Gemini provider: {provider['id']}")
    return await async_cloud_provider_manager.get_provider_with_key(provider["id"])


# Helper functions for loading data from database at startup
async def _reload_llm_faq():
    """Загружает FAQ из БД и обновляет LLM сервис."""
    if llm_service and hasattr(llm_service, "reload_faq"):
        faq_dict = await async_faq_manager.get_all()
        llm_service.reload_faq(faq_dict)


async def _reload_voice_presets():
    """Загружает пресеты из БД и обновляет voice сервисы."""
    presets_dict = await async_preset_manager.get_custom()
    for svc in [voice_service, anna_voice_service]:
        if svc and hasattr(svc, "reload_presets"):
            svc.reload_presets(presets_dict)


async def _auto_start_bridge_if_needed():
    """Auto-start CLI-OpenAI Bridge if any enabled claude_bridge provider exists."""
    from bridge_manager import bridge_manager
    from db.integration import async_cloud_provider_manager

    try:
        bridge_providers = await async_cloud_provider_manager.get_by_type(
            "claude_bridge", enabled_only=True
        )
        if not bridge_providers:
            return

        if bridge_manager.is_running:
            logger.info("🌉 Bridge already running, skipping auto-start")
            return

        logger.info("🌉 Auto-starting CLI-OpenAI Bridge (enabled claude_bridge provider found)...")
        result = await bridge_manager.start()
        if result.get("status") == "ok":
            logger.info(f"🌉 Bridge auto-started on port {result.get('port', 8787)}")
        else:
            logger.warning(f"🌉 Bridge auto-start failed: {result.get('error', 'unknown')}")
    except Exception as e:
        logger.error(f"🌉 Error during bridge auto-start: {e}")


async def _build_wiki_embeddings(wiki_rag):
    """Background task: build embedding vectors for Wiki RAG sections."""
    try:
        # Run sync build_embeddings in a thread to avoid blocking the event loop
        result = await asyncio.to_thread(wiki_rag.build_embeddings)
        if result.get("status") == "ok":
            total = result.get("total", result.get("cached", 0))
            new = result.get("new", 0)
            logger.info(f"✅ Wiki RAG embeddings: {total} секций ({new} новых)")
        elif result.get("status") == "error":
            logger.warning(f"⚠️ Wiki RAG embeddings error: {result.get('error')}")
    except Exception as e:
        logger.warning(f"⚠️ Wiki RAG embeddings build failed: {e}")


async def _load_collection_indexes(wiki_rag):
    """Background task: load per-collection BM25 indexes."""
    try:
        from db.integration import async_knowledge_collection_manager

        collections = await async_knowledge_collection_manager.get_all(enabled_only=True)
        loaded = 0
        for col in collections:
            filenames = await async_knowledge_collection_manager.get_document_filenames(col["id"])
            if filenames:
                base_dir = Path(col.get("base_dir", "wiki-pages"))
                # Run sync load_collection in a thread to avoid blocking the event loop
                await asyncio.to_thread(wiki_rag.load_collection, col["id"], filenames, base_dir)
                loaded += 1
        if loaded:
            logger.info(f"📚 Wiki RAG: загружено {loaded} коллекционных индексов")
    except Exception as e:
        logger.warning(f"⚠️ Wiki RAG collection indexes load failed: {e}")


async def _auto_start_telegram_bots():
    """Auto-start Telegram bots that have auto_start=True."""
    from db.integration import async_bot_instance_manager
    from multi_bot_manager import multi_bot_manager

    try:
        instances = await async_bot_instance_manager.get_auto_start_instances()
        if not instances:
            logger.info("📱 No Telegram bots configured for auto-start")
            return

        started = 0
        for instance in instances:
            instance_id = instance["id"]
            try:
                result = await multi_bot_manager.start_bot(instance_id)
                if result.get("status") in ["started", "already_running"]:
                    started += 1
                    logger.info(f"📱 Auto-started Telegram bot: {instance['name']}")
                else:
                    logger.warning(f"📱 Failed to auto-start bot {instance_id}: {result}")
            except Exception as e:
                logger.error(f"📱 Error auto-starting bot {instance_id}: {e}")

        if started > 0:
            logger.info(f"📱 Auto-started {started}/{len(instances)} Telegram bots")
    except Exception as e:
        logger.error(f"📱 Error during Telegram bot auto-start: {e}")


async def _auto_start_whatsapp_bots():
    """Auto-start WhatsApp bots that have auto_start=True."""
    from db.integration import async_whatsapp_instance_manager
    from whatsapp_manager import whatsapp_manager

    try:
        instances = await async_whatsapp_instance_manager.get_auto_start_instances()
        if not instances:
            logger.info("📱 No WhatsApp bots configured for auto-start")
            return

        started = 0
        for instance in instances:
            instance_id = instance["id"]
            try:
                result = await whatsapp_manager.start_bot(instance_id)
                if result.get("status") in ["started", "already_running"]:
                    started += 1
                    logger.info(f"📱 Auto-started WhatsApp bot: {instance['name']}")
                else:
                    logger.warning(f"📱 Failed to auto-start WhatsApp bot {instance_id}: {result}")
            except Exception as e:
                logger.error(f"📱 Error auto-starting WhatsApp bot {instance_id}: {e}")

        if started > 0:
            logger.info(f"📱 Auto-started {started}/{len(instances)} WhatsApp bots")
    except Exception as e:
        logger.error(f"📱 Error during WhatsApp bot auto-start: {e}")


async def _seed_system_roles():
    """Seed default RBAC roles if none exist (idempotent)."""
    try:
        count = await async_role_manager.count()
        if count > 0:
            logger.info(f"🔐 RBAC: {count} roles already exist, skipping seed")
            return

        ALL_MODULES = [
            "dashboard",
            "chat",
            "llm",
            "speech",
            "faq",
            "wiki",
            "channels",
            "sales",
            "kanban",
            "gsm",
            "system",
            "audit",
            "usage",
            "settings",
            "users",
            "claude_code",
        ]

        SYSTEM_ROLES = [
            {
                "name": "owner",
                "display_name": "Owner",
                "description": "Full system owner with all permissions",
                "permissions": dict.fromkeys(ALL_MODULES, "manage"),
            },
            {
                "name": "admin",
                "display_name": "Administrator",
                "description": "Full administrative access",
                "permissions": dict.fromkeys(ALL_MODULES, "manage"),
            },
            {
                "name": "operator",
                "display_name": "Operator",
                "description": "Day-to-day operations: chat, content, channels",
                "permissions": {
                    **dict.fromkeys(
                        [
                            "chat",
                            "llm",
                            "speech",
                            "faq",
                            "wiki",
                            "channels",
                            "sales",
                            "kanban",
                        ],
                        "edit",
                    ),
                    **dict.fromkeys(["audit", "usage", "dashboard"], "view"),
                },
            },
            {
                "name": "viewer",
                "display_name": "Viewer",
                "description": "Read-only access to key modules",
                "permissions": dict.fromkeys(
                    [
                        "dashboard",
                        "chat",
                        "llm",
                        "faq",
                        "wiki",
                        "kanban",
                        "audit",
                    ],
                    "view",
                ),
            },
        ]

        for role_def in SYSTEM_ROLES:
            await async_role_manager.create_role(
                name=role_def["name"],
                display_name=role_def["display_name"],
                description=role_def["description"],
                is_system=True,
                permissions=role_def["permissions"],
            )

        logger.info(f"🔐 RBAC: seeded {len(SYSTEM_ROLES)} system roles")
    except Exception as e:
        logger.error(f"🔐 RBAC seed failed: {e}")


async def _seed_default_workspace():
    """Seed default workspace and populate workspace_members for all users."""
    try:
        ws = await async_workspace_manager.get_default_workspace()
        if ws:
            logger.info("🏢 Workspace: default already exists, checking membership")
        else:
            await async_workspace_manager.create_default(name="Default", slug="default")
            logger.info("🏢 Workspace: created default workspace (id=1)")

        # Populate workspace_members for all users not yet in workspace 1
        _LEGACY_ROLE_MAP = {
            "admin": "admin",
            "user": "operator",
            "web": "operator",
            "guest": "viewer",
        }
        users = await async_user_manager.list_users(include_inactive=True)
        added = 0
        for u in users:
            role_name = _LEGACY_ROLE_MAP.get(u["role"], "viewer")
            await async_workspace_manager.ensure_membership(1, u["id"], role_name)
            added += 1
        if added:
            logger.info(f"🏢 Workspace: ensured {added} users in default workspace")
    except Exception as e:
        logger.error(f"🏢 Workspace seed failed: {e}")


class ConversationRequest(BaseModel):
    text: str
    session_id: Optional[str] = None


class TTSRequest(BaseModel):
    text: str
    language: str = "ru"


class OpenAISpeechRequest(BaseModel):
    """OpenAI-compatible TTS request for OpenWebUI integration"""

    model: str = "marina-voice"
    input: str
    voice: str = "marina"
    response_format: str = "wav"
    speed: float = 1.0


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request"""

    model: str = "anna-secretary-qwen"  # Format: {persona}-secretary-{backend}
    messages: List[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


@app.on_event("startup")
async def startup_event():
    """Инициализация всех сервисов при старте"""
    global \
        voice_service, \
        anna_voice_service, \
        piper_service, \
        openvoice_service, \
        stt_service, \
        llm_service, \
        streaming_tts_manager, \
        LLM_BACKEND

    logger.info(f"🚀 Запуск AI Secretary Orchestrator (mode={DEPLOYMENT_MODE})")

    # Initialize database first
    await init_database()
    await _seed_system_roles()
    await _seed_default_workspace()

    try:
        # TTS/STT services — skip entirely in cloud mode
        global current_voice_config
        if DEPLOYMENT_MODE == "cloud":
            logger.info("☁️ Cloud mode: пропускаем TTS/STT/GPU сервисы")
            piper_service = None
            openvoice_service = None
            anna_voice_service = None
            voice_service = None
            stt_service = None
            current_voice_config = {"engine": "none", "voice": "none"}
        else:
            # Инициализация Piper TTS (Dmitri, Irina) - CPU, загружаем первым
            if PIPER_AVAILABLE:
                logger.info("📦 Загрузка Piper TTS Service (CPU)...")
                try:
                    piper_service = PiperTTSService()
                except Exception as e:
                    logger.warning(f"⚠️ Piper TTS недоступен: {e}")
                    piper_service = None
            else:
                logger.info("⏭️ Piper TTS не установлен (пропускаем)")
                piper_service = None

            # Инициализация OpenVoice v2 (Марина) - GPU CC 6.1+ (P104-100)
            if OPENVOICE_AVAILABLE:
                logger.info("📦 Загрузка OpenVoice TTS Service (GPU CC 6.1+)...")
                try:
                    openvoice_service = OpenVoiceService()
                    logger.info("✅ OpenVoice v2 загружен (P104-100)")
                except Exception as e:
                    logger.warning(f"⚠️ OpenVoice недоступен: {e}")
                    openvoice_service = None
            else:
                logger.info("⏭️ OpenVoice не установлен (пропускаем)")
                openvoice_service = None

            # Инициализация XTTS (Анна) - GPU CC >= 7.0, по умолчанию
            if XTTS_AVAILABLE:
                logger.info("📦 Загрузка Voice Clone Service (XTTS - Анна)...")
                try:
                    anna_voice_service = VoiceCloneService(voice_samples_dir="./Анна")
                    logger.info(f"✅ XTTS (Анна): {len(anna_voice_service.voice_samples)} образцов")
                except Exception as e:
                    logger.warning(f"⚠️ XTTS (Анна) недоступен: {e}")
                    anna_voice_service = None
            else:
                logger.info("⏭️ XTTS не установлен (пропускаем)")
                anna_voice_service = None

            # Инициализация XTTS (Марина) - GPU CC >= 7.0, опционально
            if XTTS_AVAILABLE:
                logger.info("📦 Загрузка Voice Clone Service (XTTS - Марина)...")
                try:
                    voice_service = VoiceCloneService(voice_samples_dir="./Марина")
                    logger.info(f"✅ XTTS (Марина): {len(voice_service.voice_samples)} образцов")
                except Exception as e:
                    logger.warning(f"⚠️ XTTS (Марина) недоступен: {e}")
                    voice_service = None
            else:
                voice_service = None

            # Устанавливаем голос по умолчанию
            if anna_voice_service:
                current_voice_config = {"engine": "xtts", "voice": "anna"}
                logger.info("🎤 Голос по умолчанию: Анна (XTTS)")
            elif voice_service:
                current_voice_config = {"engine": "xtts", "voice": "marina"}
                logger.info("🎤 Голос по умолчанию: Марина (XTTS)")
            elif piper_service:
                current_voice_config = {"engine": "piper", "voice": "dmitri"}
                logger.info("🎤 Голос по умолчанию: Дмитрий (Piper)")

        # Инициализация LLM Service (vLLM или Cloud)
        # Auto-migrate legacy "gemini" backend to cloud provider system
        if LLM_BACKEND == "gemini":
            logger.info("🔄 Auto-migrating LLM_BACKEND=gemini to cloud provider...")
            gemini_provider = await _get_or_create_default_gemini_provider()
            if gemini_provider:
                LLM_BACKEND = f"cloud:{gemini_provider['id']}"
                os.environ["LLM_BACKEND"] = LLM_BACKEND
                logger.info(f"✅ Migrated to {LLM_BACKEND}")
            else:
                logger.warning("⚠️ Cannot auto-migrate gemini backend: no GEMINI_API_KEY")
                LLM_BACKEND = "vllm"

        if LLM_BACKEND == "vllm" and VLLM_AVAILABLE:
            logger.info("📦 Загрузка vLLM LLM Service...")
            try:
                llm_service = VLLMLLMService()
                if llm_service.is_available():
                    logger.info("✅ vLLM подключен")
                else:
                    logger.warning("⚠️ vLLM не отвечает, пробуем облачного провайдера...")
                    gemini_provider = await _get_or_create_default_gemini_provider()
                    if gemini_provider:
                        llm_service = CloudLLMService(gemini_provider)
                        LLM_BACKEND = f"cloud:{gemini_provider['id']}"
                        os.environ["LLM_BACKEND"] = LLM_BACKEND
                        logger.info(f"✅ Fallback на cloud: {gemini_provider['id']}")
                    else:
                        logger.warning("⚠️ Нет облачного провайдера для fallback")
            except Exception as e:
                logger.warning(f"⚠️ vLLM недоступен ({e}), пробуем облачного провайдера...")
                gemini_provider = await _get_or_create_default_gemini_provider()
                if gemini_provider:
                    llm_service = CloudLLMService(gemini_provider)
                    LLM_BACKEND = f"cloud:{gemini_provider['id']}"
                    os.environ["LLM_BACKEND"] = LLM_BACKEND
                    logger.info(f"✅ Fallback на cloud: {gemini_provider['id']}")
                else:
                    logger.warning("⚠️ Нет облачного провайдера для fallback")
                    llm_service = None
        elif LLM_BACKEND.startswith("cloud:"):
            provider_id = LLM_BACKEND.split(":", 1)[1]
            logger.info(f"☁️ LLM backend: {LLM_BACKEND} (cloud provider)")
            try:
                provider_config = await async_cloud_provider_manager.get_provider_with_key(
                    provider_id
                )
                if provider_config:
                    llm_service = CloudLLMService(provider_config)
                    logger.info(
                        f"✅ Cloud LLM: {provider_config.get('name')} "
                        f"({provider_config.get('provider_type')})"
                    )
                else:
                    logger.warning(f"⚠️ Cloud provider {provider_id} not found in DB")
                    llm_service = None
            except Exception as e:
                logger.warning(f"⚠️ Cloud LLM недоступен ({e})")
                llm_service = None
        else:
            logger.warning(f"⚠️ Unknown LLM_BACKEND={LLM_BACKEND}, trying vLLM...")
            if VLLM_AVAILABLE:
                try:
                    llm_service = VLLMLLMService()
                    if llm_service.is_available():
                        LLM_BACKEND = "vllm"
                        logger.info("✅ vLLM подключен (fallback)")
                    else:
                        llm_service = None
                except Exception:
                    llm_service = None
            else:
                llm_service = None

        # Инициализация Streaming TTS Manager
        logger.info("📦 Инициализация Streaming TTS Manager...")
        streaming_tts_manager = StreamingTTSManager(max_cache_size=50, cache_ttl=300)

        # STT (Vosk) для голосовых звонков
        try:
            from stt_service import VoskSTTService

            stt_service = VoskSTTService(language="ru", model_size="small")
            logger.info("✅ STT (Vosk) initialized")
        except Exception as stt_err:
            logger.warning(f"⚠️ STT not available: {stt_err}")
            stt_service = None

        # Load FAQ and presets from database into services
        logger.info("📦 Загрузка FAQ и пресетов из БД...")
        try:
            await _reload_llm_faq()
            await _reload_voice_presets()
            logger.info("✅ FAQ и пресеты загружены из БД")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка загрузки данных из БД: {e}")

        # Check for deprecated legacy JSON files
        legacy_files = [
            ("typical_responses.json", "FAQ"),
            ("custom_presets.json", "TTS presets"),
            ("chat_sessions.json", "chat sessions"),
            ("widget_config.json", "widget config"),
            ("telegram_config.json", "telegram config"),
        ]
        found_legacy = []
        for filename, description in legacy_files:
            if Path(filename).exists():
                found_legacy.append(f"{filename} ({description})")

        if found_legacy:
            logger.warning("=" * 60)
            logger.warning("⚠️  DEPRECATED: Найдены legacy JSON файлы:")
            for f in found_legacy:
                logger.warning(f"    • {f}")
            logger.warning("    Данные теперь хранятся в SQLite (data/secretary.db).")
            logger.warning("    Legacy файлы можно удалить после проверки миграции:")
            logger.warning("    python scripts/migrate_json_to_db.py")
            logger.warning("=" * 60)

        # Populate service container for modular routers
        from app.dependencies import get_container

        container = get_container()
        container.voice_service = voice_service
        container.anna_voice_service = anna_voice_service
        container.piper_service = piper_service
        container.openvoice_service = openvoice_service
        container.stt_service = stt_service
        container.llm_service = llm_service
        container.streaming_tts_manager = streaming_tts_manager
        container.current_voice_config = current_voice_config

        # Initialize GSM telephony service (skip in cloud mode)
        if DEPLOYMENT_MODE != "cloud":
            try:
                from app.services.gsm_service import GSMService

                gsm_service = GSMService()
                await gsm_service.initialize()
                container.gsm_service = gsm_service
                mode = "mock" if gsm_service.mock_mode else "hardware"
                logger.info(f"✅ GSM service initialized ({mode} mode)")

                # Start voice call service (auto-answer with AI assistant)
                try:
                    from app.services.gsm_voice_call import GSMVoiceCallService

                    voice_call = GSMVoiceCallService(
                        gsm_service=gsm_service,
                        stt_service=getattr(container, "stt_service", None),
                        tts_service=container.anna_voice_service or container.voice_service,
                        piper_service=container.piper_service,
                        tts_voice="xtts",  # or "piper" for CPU
                        piper_voice="irina",  # irina / dmitri
                        rag_mode="all",  # use all knowledge collections
                    )
                    await voice_call.start()
                    container.gsm_voice_call = voice_call
                    logger.info("✅ GSM Voice Call service started (auto-answer)")
                except Exception as vc_err:
                    logger.warning(f"⚠️ GSM Voice Call not available: {vc_err}")
            except Exception as gsm_err:
                logger.warning(f"⚠️ GSM service not available: {gsm_err}")

        # Initialize Internet Monitor + LLM auto-switching (skip in cloud mode)
        if DEPLOYMENT_MODE != "cloud":
            try:
                from modules.core.internet_monitor import ConnectivityStatus, InternetMonitor

                async def _switch_llm(status: ConnectivityStatus) -> str:
                    """Switch LLM backend based on internet connectivity."""
                    global llm_service, LLM_BACKEND
                    if status in (ConnectivityStatus.ONLINE, ConnectivityStatus.DEGRADED):
                        # Try cloud provider: claude_bridge first, then default, then any enabled
                        try:
                            providers = await async_cloud_provider_manager.list_providers(
                                enabled_only=True
                            )
                            provider = None
                            # Priority: claude_bridge > is_default > first enabled
                            for p in providers or []:
                                if p.get("provider_type") == "claude_bridge" and p.get("enabled"):
                                    provider = p
                                    break
                            if not provider:
                                for p in providers or []:
                                    if p.get("is_default") and p.get("enabled"):
                                        provider = p
                                        break
                            if not provider:
                                for p in providers or []:
                                    if p.get("enabled"):
                                        provider = p
                                        break
                            if provider:
                                provider = await async_cloud_provider_manager.get_provider_with_key(
                                    provider["id"]
                                )
                            if provider:
                                new_svc = CloudLLMService(provider)
                                llm_service = new_svc
                                container.llm_service = new_svc
                                ptype = provider.get("provider_type", "cloud")
                                backend = f"cloud ({ptype}: {provider.get('name', '?')})"
                                LLM_BACKEND = f"cloud:{provider['id']}"
                                return backend
                        except Exception as e:
                            logger.warning(f"Cloud LLM switch failed: {e}")
                        # Fallback to vLLM even when online
                        if VLLM_AVAILABLE:
                            try:
                                new_svc = VLLMLLMService()
                                if new_svc.is_available():
                                    llm_service = new_svc
                                    container.llm_service = new_svc
                                    LLM_BACKEND = "vllm"
                                    return "vllm (cloud unavailable)"
                            except Exception:
                                pass
                        return LLM_BACKEND  # keep current
                    else:
                        # Offline — switch to local vLLM
                        if VLLM_AVAILABLE:
                            try:
                                new_svc = VLLMLLMService()
                                if new_svc.is_available():
                                    llm_service = new_svc
                                    container.llm_service = new_svc
                                    LLM_BACKEND = "vllm"
                                    return "vllm (offline)"
                            except Exception as e:
                                logger.error(f"vLLM fallback failed: {e}")
                        return LLM_BACKEND  # keep current

                internet_monitor = InternetMonitor(check_interval=30)
                internet_monitor.set_switch_callback(_switch_llm)
                await internet_monitor.start()
                container.internet_monitor = internet_monitor
                logger.info("✅ InternetMonitor started (auto-switching LLM)")
            except Exception as im_err:
                logger.warning(f"⚠️ InternetMonitor not available: {im_err}")

        # Initialize Wiki RAG service
        try:
            from app.services.wiki_rag_service import WikiRAGService

            wiki_rag = WikiRAGService(Path("wiki-pages"))
            container.wiki_rag_service = wiki_rag

            # Initialize embedding provider for Wiki RAG (tiered: local > cloud > none)
            embedding_provider = None

            # Phase 3: Local embeddings (best quality, DEPLOYMENT_MODE=full only)
            if DEPLOYMENT_MODE != "cloud":
                try:
                    from app.services.embedding_provider import (
                        LOCAL_EMBEDDINGS_AVAILABLE,
                        LocalEmbeddingProvider,
                    )

                    if LOCAL_EMBEDDINGS_AVAILABLE:
                        embedding_provider = LocalEmbeddingProvider()
                        logger.info("✅ Wiki RAG: local embeddings (sentence-transformers)")
                except Exception as local_err:
                    logger.debug(f"Wiki RAG: local embeddings not available: {local_err}")

            # Phase 2: Cloud embeddings from active LLM provider
            if not embedding_provider and llm_service and hasattr(llm_service, "config"):
                try:
                    cloud_config = llm_service.config
                    provider_type = cloud_config.get("provider_type", "")
                    api_key = cloud_config.get("api_key", "")

                    if provider_type == "gemini" and api_key:
                        from app.services.embedding_provider import GeminiEmbeddingProvider

                        embedding_provider = GeminiEmbeddingProvider(api_key=api_key)
                        logger.info("✅ Wiki RAG: cloud embeddings (Gemini)")
                    elif api_key and cloud_config.get("base_url"):
                        from app.services.embedding_provider import OpenAIEmbeddingProvider

                        embedding_provider = OpenAIEmbeddingProvider(
                            api_key=api_key,
                            base_url=cloud_config["base_url"],
                        )
                        logger.info("✅ Wiki RAG: cloud embeddings (OpenAI-compatible)")
                except Exception as cloud_err:
                    logger.debug(f"Wiki RAG: cloud embeddings not available: {cloud_err}")

            if embedding_provider:
                wiki_rag.set_embedding_provider(embedding_provider)
                # Build embeddings in background
                asyncio.get_event_loop().create_task(_build_wiki_embeddings(wiki_rag))
            else:
                logger.info("📚 Wiki RAG: BM25 only (no embedding provider)")

            # Load per-collection indexes in background
            asyncio.get_event_loop().create_task(_load_collection_indexes(wiki_rag))

        except Exception as wiki_err:
            logger.warning(f"⚠️ Wiki RAG service not available: {wiki_err}")

        logger.info("✅ Service container populated for modular routers")

        # Auto-start Telegram bots that were running before restart
        await _auto_start_telegram_bots()

        # Auto-start WhatsApp bots that were running before restart
        await _auto_start_whatsapp_bots()

        # Auto-start bridge if enabled claude_bridge provider exists
        await _auto_start_bridge_if_needed()

        # Start background session cleanup (hourly)
        async def _cleanup_expired_sessions():
            while True:
                await asyncio.sleep(3600)
                try:
                    from db.integration import async_session_manager

                    count = await async_session_manager.cleanup_expired(days=7)
                    if count > 0:
                        logger.info(f"Cleaned up {count} expired sessions")
                except Exception as e:
                    logger.warning(f"Session cleanup error: {e}")

        asyncio.get_event_loop().create_task(_cleanup_expired_sessions())

        # Start background VACUUM (first run after 24h, then weekly)
        async def _periodic_vacuum():
            await asyncio.sleep(24 * 3600)  # first run after 24 h
            while True:
                try:
                    from db.database import run_vacuum

                    await run_vacuum()
                except Exception as e:
                    logger.warning("Periodic VACUUM failed: %s", e)
                await asyncio.sleep(7 * 24 * 3600)  # then every 7 days

        asyncio.get_event_loop().create_task(_periodic_vacuum())

        # Periodic GitHub → Kanban sync (every 15 min)
        async def _periodic_kanban_sync():
            await asyncio.sleep(60)  # first run after 1 min
            while True:
                try:
                    from app.services.github_kanban_sync import sync_all_issues
                    from db.integration import async_kanban_project_manager

                    projects = await async_kanban_project_manager.get_all_projects()
                    for proj in projects:
                        if proj.get("sync_enabled") and proj.get("has_token", False):
                            try:
                                result = await sync_all_issues(proj["id"])
                                if result["created"] > 0:
                                    logger.info(
                                        f"Kanban sync {proj['name']}: "
                                        f"+{result['created']} new, {result['total']} total"
                                    )
                            except Exception as e:
                                logger.warning(f"Kanban sync failed for {proj['name']}: {e}")
                except Exception as e:
                    logger.warning(f"Kanban periodic sync error: {e}")
                await asyncio.sleep(15 * 60)  # every 15 min

        asyncio.get_event_loop().create_task(_periodic_kanban_sync())

        # Periodic WooCommerce dataset sync — daily at 02:00 MSK (23:00 UTC)
        async def _periodic_woocommerce_sync():
            await asyncio.sleep(120)  # warmup
            while True:
                now = datetime.utcnow()
                target = now.replace(hour=23, minute=0, second=0, microsecond=0)
                if target <= now:
                    target += timedelta(days=1)
                wait_seconds = (target - now).total_seconds()
                logger.info("WooCommerce auto-sync scheduled in %.1fh", wait_seconds / 3600)
                await asyncio.sleep(wait_seconds)
                try:
                    from modules.ecommerce.service import woocommerce_service
                    from modules.ecommerce.sync import run_woocommerce_sync

                    config = await woocommerce_service.get_config()
                    if not config or not config.get("sync_enabled"):
                        continue
                    result = await run_woocommerce_sync()
                    logger.info(
                        "WooCommerce auto-sync: %d products, %d files",
                        result["products"],
                        result["files_written"],
                    )
                except Exception as e:
                    logger.warning("WooCommerce auto-sync error: %s", e)
                    await asyncio.sleep(3600)  # on error retry in 1h

        asyncio.get_event_loop().create_task(_periodic_woocommerce_sync())

        logger.info("✅ Основные сервисы загружены успешно")

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🛑 Shutting down AI Secretary Orchestrator")
    await shutdown_database()
    logger.info("✅ Shutdown complete")


@app.get("/")
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


@app.get("/health")
async def health_check():
    """Проверка здоровья всех сервисов"""
    # Используем llm_service из container (может быть обновлён через router)
    from app.dependencies import get_container

    container = get_container()
    current_llm_service = container.llm_service if container.llm_service else llm_service

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
        "voice_clone_xtts_anna": anna_voice_service is not None,
        "voice_clone_xtts_marina": voice_service is not None,
        "voice_clone_openvoice": openvoice_service is not None,
        "piper_tts": piper_service is not None,
        "stt": stt_service is not None,
        "llm": current_llm_service is not None,
        "llm_backend": llm_backend_type,
        "streaming_tts": streaming_tts_manager is not None,
        "current_voice": current_voice_config,
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
    if streaming_tts_manager is not None:
        result["streaming_tts_stats"] = streaming_tts_manager.get_stats()

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


@app.get("/admin/deployment-mode")
async def get_deployment_mode():
    """Return current deployment mode for frontend."""
    return {"mode": DEPLOYMENT_MODE}


def synthesize_with_current_voice(text: str, output_path: str, language: str = "ru"):
    """
    Синтезирует речь с текущим выбранным голосом.
    Учитывает current_voice_config.

    Engines:
    - piper: CPU, быстрый, предобученные голоса (dmitri, irina)
    - openvoice: GPU CC 6.1+, клонирование голоса (marina_openvoice)
    - xtts: GPU CC >= 7.0, лучшее качество клонирования (anna, marina)
    """
    engine = current_voice_config["engine"]
    voice = current_voice_config["voice"]

    if engine == "piper" and piper_service:
        logger.info(f"🎙️ Piper синтез ({voice}): '{text[:40]}...'")
        piper_service.synthesize_to_file(text, output_path, voice=voice)
    elif engine == "openvoice" and openvoice_service:
        logger.info(f"🎙️ OpenVoice синтез (Марина): '{text[:40]}...'")
        openvoice_service.synthesize_to_file(text, output_path, language=language)
    elif engine == "xtts" and voice == "anna" and anna_voice_service:
        logger.info(f"🎙️ XTTS синтез (Анна): '{text[:40]}...'")
        anna_voice_service.synthesize_to_file(text, output_path, language=language)
    elif engine == "xtts" and voice == "marina" and voice_service:
        logger.info(f"🎙️ XTTS синтез (Марина): '{text[:40]}...'")
        voice_service.synthesize_to_file(text, output_path, language=language)
    elif anna_voice_service:
        # Fallback to Анна if available (default)
        logger.info(f"🎙️ XTTS синтез (Анна fallback): '{text[:40]}...'")
        anna_voice_service.synthesize_to_file(text, output_path, language=language)
    elif voice_service:
        # Fallback to Марина if available
        logger.info(f"🎙️ XTTS синтез (Марина fallback): '{text[:40]}...'")
        voice_service.synthesize_to_file(text, output_path, language=language)
    elif openvoice_service:
        # Fallback to OpenVoice if XTTS not available
        logger.info(f"🎙️ OpenVoice синтез (fallback): '{text[:40]}...'")
        openvoice_service.synthesize_to_file(text, output_path, language=language)
    elif piper_service:
        # Fallback to Piper
        logger.info(f"🎙️ Piper синтез (fallback): '{text[:40]}...'")
        piper_service.synthesize_to_file(text, output_path, voice="irina")
    else:
        raise RuntimeError("No TTS service available")


@app.post("/tts")
async def text_to_speech(request: TTSRequest):
    """
    Синтез речи с текущим выбранным голосом
    """
    if not voice_service and not piper_service:
        raise HTTPException(status_code=503, detail="No TTS service initialized")

    try:
        # Генерируем уникальное имя файла
        output_file = TEMP_DIR / f"tts_{datetime.now().timestamp()}.wav"

        # Синтезируем с текущим голосом
        synthesize_with_current_voice(
            text=request.text, output_path=str(output_file), language=request.language
        )

        # Возвращаем файл
        return FileResponse(path=output_file, media_type="audio/wav", filename="response.wav")

    except Exception as e:
        logger.error(f"❌ TTS Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/stt")
async def speech_to_text(audio: UploadFile = File(...)):
    """
    Распознавание речи из аудио файла
    """
    if not stt_service:
        raise HTTPException(status_code=503, detail="STT service not initialized")

    try:
        # Сохраняем загруженный файл
        temp_audio = TEMP_DIR / f"stt_{datetime.now().timestamp()}_{audio.filename}"

        with open(temp_audio, "wb") as f:
            content = await audio.read()
            f.write(content)

        # Распознаем
        result = stt_service.transcribe(temp_audio, language="ru")

        # Удаляем временный файл
        temp_audio.unlink()

        return {
            "text": result["text"],
            "language": result["language"],
            "segments_count": len(result.get("segments", [])),
        }

    except Exception as e:
        logger.error(f"❌ STT Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
async def chat(request: ConversationRequest):
    """
    Получить ответ от LLM
    """
    if not llm_service:
        raise HTTPException(status_code=503, detail="LLM service not initialized")

    try:
        response = llm_service.generate_response(request.text)

        return {"response": response, "session_id": request.session_id}

    except Exception as e:
        logger.error(f"❌ LLM Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/process_call")
async def process_call(audio: UploadFile = File(...)):
    """
    Полный цикл обработки звонка:
    1. STT - распознавание речи
    2. LLM - генерация ответа
    3. TTS - синтез речи

    Возвращает аудио с ответом секретаря
    """
    call_id = f"call_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    logger.info(f"📞 Обработка звонка {call_id}")

    try:
        # 1. Сохраняем входящий аудио
        input_audio = CALLS_LOG_DIR / f"{call_id}_input.wav"
        with open(input_audio, "wb") as f:
            content = await audio.read()
            f.write(content)

        # 2. Распознаем речь (STT)
        logger.info(f"🎧 STT для {call_id}")
        stt_result = stt_service.transcribe(input_audio, language="ru")
        recognized_text = stt_result["text"]
        logger.info(f"📝 Распознано: {recognized_text}")

        # Сохраняем транскрипцию
        with open(CALLS_LOG_DIR / f"{call_id}_transcript.txt", "w") as f:
            f.write(f"USER: {recognized_text}\n")

        # 3. Генерируем ответ (LLM)
        logger.info(f"🤖 LLM для {call_id}")
        llm_response = llm_service.generate_response(recognized_text)
        logger.info(f"💬 Ответ: {llm_response}")

        # Дополняем транскрипцию
        with open(CALLS_LOG_DIR / f"{call_id}_transcript.txt", "a") as f:
            f.write(f"ASSISTANT: {llm_response}\n")

        # 4. Синтезируем ответ (TTS)
        logger.info(f"🎙️  TTS для {call_id}")
        output_audio = CALLS_LOG_DIR / f"{call_id}_output.wav"
        voice_service.synthesize_to_file(
            text=llm_response, output_path=str(output_audio), language="ru"
        )

        logger.info(f"✅ Звонок {call_id} обработан")

        # 5. Возвращаем аудио ответ
        return FileResponse(
            path=output_audio,
            media_type="audio/wav",
            filename=f"{call_id}_response.wav",
            headers={
                "X-Call-ID": call_id,
                "X-Recognized-Text": recognized_text,
                "X-Response-Text": llm_response,
            },
        )

    except Exception as e:
        logger.error(f"❌ Ошибка обработки звонка {call_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reset_conversation")
async def reset_conversation():
    """Сброс истории диалога"""
    if llm_service:
        llm_service.reset_conversation()
        return {"status": "ok", "message": "Conversation history reset"}
    raise HTTPException(status_code=503, detail="LLM service not initialized")


# ============== OpenAI-Compatible Endpoints for OpenWebUI ==============


@app.get("/v1/models")
@app.get("/v1/models/")
async def list_models():
    """OpenAI-compatible models list for OpenWebUI"""
    # Определяем backend и суффикс для имени модели
    if llm_service and hasattr(llm_service, "api_url"):
        # vLLM backend - проверяем модель
        model_name = getattr(llm_service, "model_name", "unknown")
        if model_name == "lydia" or "qwen" in model_name.lower():
            backend_suffix = "qwen"
            backend_desc = "Qwen2.5-7B + LoRA"
        elif "llama" in model_name.lower():
            backend_suffix = "llama"
            backend_desc = "Llama-3.1-8B"
        else:
            backend_suffix = "vllm"
            backend_desc = model_name
    elif llm_service and isinstance(llm_service, CloudLLMService):
        backend_suffix = "cloud"
        ptype = getattr(llm_service, "provider_type", "cloud")
        backend_desc = f"{ptype}: {getattr(llm_service, 'model_name', 'unknown')}"
    else:
        backend_suffix = "cloud"
        backend_desc = "Cloud AI"

    return {
        "object": "list",
        "data": [
            {
                "id": f"anna-secretary-{backend_suffix}",
                "object": "model",
                "created": 1700000000,
                "owned_by": "ai-secretary",
                "permission": [],
                "root": f"anna-secretary-{backend_suffix}",
                "parent": None,
                "description": f"Анна - цифровой секретарь ({backend_desc})",
            },
            {
                "id": f"marina-secretary-{backend_suffix}",
                "object": "model",
                "created": 1700000000,
                "owned_by": "ai-secretary",
                "permission": [],
                "root": f"marina-secretary-{backend_suffix}",
                "parent": None,
                "description": f"Марина - цифровой секретарь ({backend_desc})",
            },
        ],
    }


@app.get("/v1/voices")
async def list_voices():
    """List available voices"""
    voices = []
    if anna_voice_service:
        voices.append({"voice_id": "anna", "name": "Анна", "language": "ru"})
    if voice_service:
        voices.append({"voice_id": "marina", "name": "Марина", "language": "ru"})
    if piper_service:
        voices.append({"voice_id": "dmitri", "name": "Дмитрий", "language": "ru"})
        voices.append({"voice_id": "irina", "name": "Ирина", "language": "ru"})
    return {"voices": voices}


@app.post("/v1/audio/speech")
async def openai_speech(request: OpenAISpeechRequest):
    """
    OpenAI-compatible TTS endpoint for OpenWebUI integration
    POST /v1/audio/speech

    Оптимизация: сначала проверяет кэш streaming TTS manager.
    Если аудио уже было предсинтезировано во время streaming LLM - возвращает мгновенно.
    """
    if not voice_service and not piper_service:
        raise HTTPException(status_code=503, detail="No TTS service initialized")

    try:
        output_file = TEMP_DIR / f"speech_{datetime.now().timestamp()}.wav"
        start_time = time.time()

        # Проверяем кэш streaming TTS (только для XTTS)
        cached_audio = None
        if current_voice_config["engine"] == "xtts" and streaming_tts_manager is not None:
            cached_audio = streaming_tts_manager.get_cached_audio(request.input)

        if cached_audio is not None:
            # Cache HIT - используем предсинтезированное аудио
            audio_data, sample_rate = cached_audio
            sf.write(str(output_file), audio_data, sample_rate)
            elapsed = time.time() - start_time
            logger.info(f"⚡ TTS из кэша за {elapsed:.3f}s (vs ~5-10s обычный синтез)")
        else:
            # Cache MISS - синтезируем с текущим голосом
            synthesize_with_current_voice(
                text=request.input, output_path=str(output_file), language="ru"
            )
            elapsed = time.time() - start_time
            logger.info(f"🎙️ TTS синтезирован за {elapsed:.2f}s")

        return FileResponse(path=output_file, media_type="audio/wav", filename="speech.wav")

    except Exception as e:
        logger.error(f"❌ OpenAI TTS Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """
    OpenAI-compatible chat completions endpoint for OpenWebUI
    Supports both streaming and non-streaming responses.
    При streaming - запускает фоновый синтез TTS по предложениям.
    """
    if not llm_service:
        raise HTTPException(status_code=503, detail="LLM service not initialized")

    logger.info(
        f"💬 Chat completions request: stream={request.stream}, messages={len(request.messages)}"
    )

    # Конвертируем Pydantic модели в dict
    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    if request.stream:
        # Streaming response (SSE) с фоновым синтезом TTS
        async def generate_stream():
            created = int(time.time())
            chunk_id = f"chatcmpl-{created}"
            session_id = f"tts-{created}"

            # Начинаем сессию streaming TTS если сервисы доступны
            use_streaming_tts = streaming_tts_manager is not None and voice_service is not None

            if use_streaming_tts:
                streaming_tts_manager.start_session(session_id)
                logger.info(f"🎬 Streaming TTS активирован для сессии {session_id}")

            try:
                for text_chunk in llm_service.generate_response_from_messages(
                    messages, stream=True
                ):
                    # Отправляем chunk клиенту
                    chunk_data = {
                        "id": chunk_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": request.model,
                        "choices": [
                            {"index": 0, "delta": {"content": text_chunk}, "finish_reason": None}
                        ],
                    }
                    yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"

                    # Параллельно добавляем chunk в streaming TTS manager
                    if use_streaming_tts and text_chunk:
                        streaming_tts_manager.add_text_chunk(session_id, text_chunk, voice_service)

                # Final chunk
                final_chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": request.model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
                yield f"data: {json.dumps(final_chunk)}\n\n"
                yield "data: [DONE]\n\n"

                # Завершаем сессию TTS (склеивает и кэширует аудио)
                if use_streaming_tts:
                    # Запускаем в отдельном потоке чтобы не блокировать response
                    threading.Thread(
                        target=streaming_tts_manager.finish_session,
                        args=(session_id, voice_service),
                        daemon=True,
                    ).start()

            except Exception as e:
                logger.error(f"❌ Streaming error: {e}")
                error_chunk = {"error": {"message": str(e), "type": "server_error"}}
                yield f"data: {json.dumps(error_chunk)}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
    else:
        # Non-streaming response
        try:
            response_text = llm_service.generate_response_from_messages(messages, stream=False)

            # Consume generator if it returns one
            if hasattr(response_text, "__iter__") and not isinstance(response_text, str):
                response_text = "".join(response_text)

            return {
                "id": f"chatcmpl-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": request.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": response_text},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
        except Exception as e:
            logger.error(f"❌ Chat completions error: {e}")
            raise HTTPException(status_code=500, detail=str(e))


# ============== Admin Web Interface ==============
# Vue 3 admin panel served from /admin (see Static Files section below)


# ============== Admin API Endpoints ==============

# ============== Auth Endpoints ==============


@app.post("/admin/auth/login", response_model=LoginResponse)
async def admin_login(request: LoginRequest, req: Request):
    """
    Authenticate user and return JWT token.

    Default credentials: admin / admin
    Set ADMIN_USERNAME and ADMIN_PASSWORD_HASH env vars for production.
    """
    user = await authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    response = await create_session(
        username=user.username,
        role=user.role,
        user_id=user.id,
        ip=req.client.host if req.client else None,
        user_agent=req.headers.get("user-agent"),
    )

    # Audit log
    await async_audit_logger.log(
        action="login", resource="auth", user_id=user.username, details={"role": user.role}
    )

    return response


@app.get("/admin/auth/me")
async def admin_get_current_user(user: User = Depends(get_current_user)):
    """Get current authenticated user info"""
    return {"username": user.username, "role": user.role}


@app.get("/admin/auth/status")
async def admin_auth_status():
    """Get authentication configuration status"""
    return get_auth_status()


# ============== Admin Models ==============


class AdminTTSPresetRequest(BaseModel):
    """Запрос на изменение пресета TTS"""

    preset: str  # warm, calm, energetic, natural, neutral


class AdminLLMPromptRequest(BaseModel):
    """Запрос на изменение системного промпта"""

    prompt: str


class AdminLLMModelRequest(BaseModel):
    """Запрос на изменение модели LLM"""

    model: str  # gemini-2.5-flash, gemini-2.5-pro


class AdminTTSTestRequest(BaseModel):
    """Запрос на тестовый синтез"""

    text: str
    preset: str = "natural"


@app.get("/admin/status")
async def admin_status():
    """Полный статус системы для админки"""
    import torch

    status = {
        "orchestrator": "running",
        "services": {
            "voice_clone": voice_service is not None,
            "llm": llm_service is not None,
            "stt": stt_service is not None,
            "streaming_tts": streaming_tts_manager is not None,
            "piper_tts": piper_service is not None,
        },
        "gpu": None,
        "streaming_tts_stats": None,
        "llm_config": None,
        "tts_config": None,
    }

    # GPU информация
    if torch.cuda.is_available():
        gpu_info = []
        for i in range(torch.cuda.device_count()):
            try:
                name = torch.cuda.get_device_name(i)
                total = torch.cuda.get_device_properties(i).total_memory / (1024**3)
                allocated = torch.cuda.memory_allocated(i) / (1024**3)
                gpu_info.append(
                    {
                        "id": i,
                        "name": name,
                        "total_gb": round(total, 2),
                        "used_gb": round(allocated, 2),
                    }
                )
            except Exception:
                pass
        status["gpu"] = gpu_info

    # Streaming TTS статистика
    if streaming_tts_manager:
        status["streaming_tts_stats"] = streaming_tts_manager.get_stats()

    # LLM конфигурация
    if llm_service:
        if hasattr(llm_service, "get_config"):
            status["llm_config"] = llm_service.get_config()
        else:
            # Для vLLM и других сервисов без get_config
            status["llm_config"] = {
                "model_name": getattr(llm_service, "model_name", "unknown"),
                "api_url": getattr(llm_service, "api_url", None),
                "backend": (
                    "vllm"
                    if hasattr(llm_service, "api_url")
                    else f"cloud:{getattr(llm_service, 'provider_id', 'unknown')}"
                    if isinstance(llm_service, CloudLLMService)
                    else "unknown"
                ),
            }

    # TTS конфигурация
    xtts_svc = anna_voice_service or voice_service
    if xtts_svc:
        status["tts_config"] = {
            "device": xtts_svc.device,
            "default_preset": xtts_svc.default_preset,
            "samples_count": len(xtts_svc.voice_samples),
            "cache_dir": str(xtts_svc.cache_dir),
        }

    return status


@app.get("/admin/llm/prompt")
async def admin_get_llm_prompt():
    """Получить текущий системный промпт LLM"""
    if llm_service:
        persona = getattr(llm_service, "current_persona", None) or os.getenv(
            "SECRETARY_PERSONA", "anna"
        )
        return {
            "prompt": llm_service.system_prompt,
            "model": llm_service.model_name,
            "persona": persona,
        }
    raise HTTPException(status_code=503, detail="LLM service not initialized")


@app.post("/admin/llm/prompt")
async def admin_set_llm_prompt(request: AdminLLMPromptRequest):
    """Установить новый системный промпт LLM"""
    if llm_service:
        llm_service.set_system_prompt(request.prompt)
        return {
            "status": "ok",
            "prompt": request.prompt[:100] + "..." if len(request.prompt) > 100 else request.prompt,
        }
    raise HTTPException(status_code=503, detail="LLM service not initialized")


@app.get("/admin/llm/model")
async def admin_get_llm_model():
    """Получить текущую модель LLM"""
    if llm_service:
        return {"model": llm_service.model_name}
    raise HTTPException(status_code=503, detail="LLM service not initialized")


@app.post("/admin/llm/model")
async def admin_set_llm_model(request: AdminLLMModelRequest):
    """Изменить модель LLM"""
    allowed_models = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]

    if request.model not in allowed_models:
        raise HTTPException(
            status_code=400,
            detail=f"Неизвестная модель: {request.model}. Доступные: {allowed_models}",
        )

    if llm_service:
        try:
            llm_service.set_model(request.model)
            return {"status": "ok", "model": request.model}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    raise HTTPException(status_code=503, detail="LLM service not initialized")


@app.delete("/admin/llm/history")
async def admin_clear_llm_history():
    """Очистить историю диалога LLM"""
    if llm_service:
        count = len(llm_service.conversation_history)
        llm_service.reset_conversation()
        return {"status": "ok", "cleared_messages": count}
    raise HTTPException(status_code=503, detail="LLM service not initialized")


@app.get("/admin/llm/history")
async def admin_get_llm_history():
    """Получить историю диалога LLM"""
    if llm_service:
        return {
            "history": llm_service.conversation_history,
            "count": len(llm_service.conversation_history),
        }
    raise HTTPException(status_code=503, detail="LLM service not initialized")


# ============== Voice Selection API ==============


class AdminVoiceRequest(BaseModel):
    voice: str  # anna / marina / dmitri / irina


@app.get("/admin/voices")
async def admin_get_voices():
    """Получить список всех доступных голосов"""
    voices = []

    # XTTS голос (Анна) - требует GPU CC >= 7.0 (по умолчанию)
    if anna_voice_service:
        voices.append(
            {
                "id": "anna",
                "name": "Анна (XTTS)",
                "engine": "xtts",
                "description": "Клонированный голос Гули (XTTS v2, GPU CC >= 7.0)",
                "available": True,
                "samples_count": len(anna_voice_service.voice_samples),
                "default": True,
            }
        )

    # XTTS голос (Марина) - требует GPU CC >= 7.0
    if voice_service:
        voices.append(
            {
                "id": "marina",
                "name": "Марина (XTTS)",
                "engine": "xtts",
                "description": "Клонированный голос Лидии (XTTS v2, GPU CC >= 7.0)",
                "available": True,
                "samples_count": len(voice_service.voice_samples),
            }
        )

    # OpenVoice голос (Марина) - работает на GPU CC 6.1+
    if openvoice_service:
        voices.append(
            {
                "id": "marina_openvoice",
                "name": "Марина (OpenVoice)",
                "engine": "openvoice",
                "description": "Клонированный голос (OpenVoice v2, GPU CC 6.1+)",
                "available": True,
                "samples_count": len(openvoice_service.voice_samples)
                if openvoice_service.voice_samples
                else 0,
            }
        )

    # Piper голоса (CPU)
    if piper_service:
        piper_voices = piper_service.get_available_voices()
        for voice_id, info in piper_voices.items():
            voices.append(
                {
                    "id": voice_id,
                    "name": info["name"],
                    "engine": "piper",
                    "description": info["description"],
                    "available": info["available"],
                }
            )

    return {
        "voices": voices,
        "current": current_voice_config,
    }


@app.get("/admin/voice")
async def admin_get_current_voice():
    """Получить текущий выбранный голос"""
    return current_voice_config


@app.post("/admin/voice")
async def admin_set_voice(request: AdminVoiceRequest):
    """Установить активный голос"""
    global current_voice_config

    voice_id = request.voice.lower()

    # Проверяем доступность голоса
    if voice_id == "anna":
        if not anna_voice_service:
            raise HTTPException(
                status_code=503, detail="XTTS service (Анна) not available (requires GPU CC >= 7.0)"
            )
        current_voice_config = {"engine": "xtts", "voice": "anna"}
        logger.info("🎤 Голос изменён на: Анна (XTTS)")

    elif voice_id == "marina":
        if not voice_service:
            raise HTTPException(
                status_code=503,
                detail="XTTS service (Марина) not available (requires GPU CC >= 7.0)",
            )
        current_voice_config = {"engine": "xtts", "voice": "marina"}
        logger.info("🎤 Голос изменён на: Марина (XTTS)")

    elif voice_id == "marina_openvoice":
        if not openvoice_service:
            raise HTTPException(status_code=503, detail="OpenVoice service not available")
        current_voice_config = {"engine": "openvoice", "voice": "marina_openvoice"}
        logger.info("🎤 Голос изменён на: Марина (OpenVoice)")

    elif voice_id in ["dmitri", "irina"]:
        if not piper_service:
            raise HTTPException(status_code=503, detail="Piper TTS service not available")
        piper_voices = piper_service.get_available_voices()
        if voice_id not in piper_voices or not piper_voices[voice_id]["available"]:
            raise HTTPException(status_code=400, detail=f"Voice model not found: {voice_id}")
        current_voice_config = {"engine": "piper", "voice": voice_id}
        logger.info(f"🎤 Голос изменён на: {piper_voices[voice_id]['name']} (Piper)")

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown voice: {voice_id}. Available: anna, marina, marina_openvoice, dmitri, irina",
        )

    # Sync with service container for modular routers
    from app.dependencies import get_container

    container = get_container()
    container.current_voice_config = current_voice_config

    return {"status": "ok", **current_voice_config}


@app.post("/admin/voice/test")
async def admin_test_voice(request: AdminVoiceRequest):
    """Тестовый синтез выбранным голосом"""
    voice_id = request.voice.lower()
    test_text = "Здравствуйте! Это тестовое сообщение для проверки голоса."

    output_path = TEMP_DIR / f"voice_test_{voice_id}_{int(time.time())}.wav"

    try:
        if voice_id == "anna":
            if not anna_voice_service:
                raise HTTPException(
                    status_code=503, detail="XTTS (Анна) not available (requires GPU CC >= 7.0)"
                )
            anna_voice_service.synthesize_to_file(test_text, str(output_path), preset="natural")

        elif voice_id == "marina":
            if not voice_service:
                raise HTTPException(
                    status_code=503, detail="XTTS (Марина) not available (requires GPU CC >= 7.0)"
                )
            voice_service.synthesize_to_file(test_text, str(output_path), preset="natural")

        elif voice_id == "marina_openvoice":
            if not openvoice_service:
                raise HTTPException(status_code=503, detail="OpenVoice not available")
            openvoice_service.synthesize_to_file(test_text, str(output_path), language="ru")

        elif voice_id in ["dmitri", "irina"]:
            if not piper_service:
                raise HTTPException(status_code=503, detail="Piper not available")
            piper_service.synthesize_to_file(test_text, str(output_path), voice=voice_id)

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown voice: {voice_id}. Available: anna, marina, marina_openvoice, dmitri, irina",
            )

        return FileResponse(output_path, media_type="audio/wav", filename=f"test_{voice_id}.wav")

    except Exception as e:
        logger.error(f"❌ Ошибка тестового синтеза: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def get_current_tts_service():
    """Возвращает текущий TTS сервис и параметры на основе конфигурации"""
    engine = current_voice_config["engine"]
    voice = current_voice_config["voice"]

    if engine == "xtts" and voice == "anna":
        return anna_voice_service, {"preset": "natural"}
    elif engine == "xtts" and voice == "marina":
        return voice_service, {"preset": "natural"}
    elif engine == "piper":
        return piper_service, {"voice": voice}
    else:
        # Default to anna if available
        return anna_voice_service or voice_service, {"preset": "natural"}


# ============== Extended Admin API Endpoints ==============


# Pydantic models for new endpoints
class AdminBackendRequest(BaseModel):
    backend: str  # "vllm" or "cloud:{provider_id}"
    stop_unused: bool = False  # Остановить неиспользуемый сервис (vLLM) для освобождения GPU


class CloudProviderCreate(BaseModel):
    """Create cloud LLM provider"""

    name: str
    provider_type: str  # gemini, kimi, openai, claude, deepseek, custom
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: str = ""
    enabled: bool = True
    is_default: bool = False
    config: Optional[Dict] = None
    description: Optional[str] = None


class CloudProviderUpdate(BaseModel):
    """Update cloud LLM provider"""

    name: Optional[str] = None
    provider_type: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None
    enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    config: Optional[Dict] = None
    description: Optional[str] = None


class AdminPersonaRequest(BaseModel):
    persona: str  # "anna" or "marina"


class AdminLLMParamsRequest(BaseModel):
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    repetition_penalty: Optional[float] = None


class AdminXTTSParamsRequest(BaseModel):
    temperature: Optional[float] = None
    repetition_penalty: Optional[float] = None
    top_k: Optional[int] = None
    top_p: Optional[float] = None
    speed: Optional[float] = None
    gpt_cond_len: Optional[int] = None
    gpt_cond_chunk_len: Optional[int] = None


class AdminPiperParamsRequest(BaseModel):
    speed: float = 1.0


class AdminCustomPresetRequest(BaseModel):
    name: str
    params: dict


class AdminFAQRequest(BaseModel):
    trigger: str
    response: str


class AdminFAQTestRequest(BaseModel):
    text: str


class AdminWidgetConfigRequest(BaseModel):
    enabled: bool = True
    title: str = "AI Ассистент"
    greeting: str = "Здравствуйте! Компания Шаервэй Ди-Иджитал, чем могу помочь?"
    placeholder: str = "Введите сообщение..."
    primary_color: str = "#c2410c"
    position: str = "right"  # "left" or "right"
    allowed_domains: List[str] = []
    tunnel_url: str = ""


class AdminTelegramConfigRequest(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    api_url: str = "http://localhost:8002"
    allowed_users: List[int] = []
    admin_users: List[int] = []
    welcome_message: str = "Здравствуйте! Я AI-ассистент компании Шаервэй. Чем могу помочь?"
    unauthorized_message: str = "Извините, у вас нет доступа к этому боту."
    error_message: str = "Произошла ошибка. Попробуйте позже."
    typing_enabled: bool = True


class AdminFinetuneConfigRequest(BaseModel):
    lora_rank: Optional[int] = None
    lora_alpha: Optional[int] = None
    batch_size: Optional[int] = None
    gradient_accumulation_steps: Optional[int] = None
    learning_rate: Optional[float] = None
    num_epochs: Optional[int] = None
    max_seq_length: Optional[int] = None
    output_dir: Optional[str] = None


class AdminAdapterRequest(BaseModel):
    adapter: str


class AdminAuditQueryRequest(BaseModel):
    action: Optional[str] = None
    resource: Optional[str] = None
    user_id: Optional[str] = None
    from_date: Optional[str] = None  # ISO format
    to_date: Optional[str] = None  # ISO format
    limit: int = 100
    offset: int = 0


# ============== Chat Models & Manager ==============


class ChatMessageModel(BaseModel):
    id: str
    role: str
    content: str
    timestamp: str
    edited: bool = False


class ChatSessionModel(BaseModel):
    id: str
    title: str
    messages: List[ChatMessageModel]
    system_prompt: Optional[str] = None
    created: str
    updated: str


class CreateSessionRequest(BaseModel):
    title: Optional[str] = None
    system_prompt: Optional[str] = None


class UpdateSessionRequest(BaseModel):
    title: Optional[str] = None
    system_prompt: Optional[str] = None


class LLMOverrideConfig(BaseModel):
    llm_backend: Optional[str] = None  # "vllm" or "cloud:provider-id"
    system_prompt: Optional[str] = None
    llm_params: Optional[dict] = None


class SendMessageRequest(BaseModel):
    content: str
    llm_override: Optional[LLMOverrideConfig] = None


class EditMessageRequest(BaseModel):
    content: str


# ============== Services Endpoints ==============


@app.get("/admin/services/status")
async def admin_services_status():
    """Получить статус всех сервисов"""
    manager = get_service_manager()
    status = manager.get_all_status()

    # Добавляем статус внутренних сервисов из orchestrator
    status["services"]["xtts_anna"]["is_running"] = anna_voice_service is not None
    status["services"]["xtts_marina"]["is_running"] = voice_service is not None
    status["services"]["piper"]["is_running"] = piper_service is not None
    status["services"]["openvoice"]["is_running"] = openvoice_service is not None
    status["services"]["orchestrator"]["is_running"] = True

    return status


@app.post("/admin/services/{service}/start")
async def admin_start_service(service: str):
    """Запустить сервис"""
    manager = get_service_manager()
    return await manager.start_service(service)


@app.post("/admin/services/{service}/stop")
async def admin_stop_service(service: str):
    """Остановить сервис"""
    manager = get_service_manager()
    return await manager.stop_service(service)


@app.post("/admin/services/{service}/restart")
async def admin_restart_service(service: str):
    """Перезапустить сервис"""
    manager = get_service_manager()
    return await manager.restart_service(service)


@app.post("/admin/services/start-all")
async def admin_start_all_services():
    """Запустить все внешние сервисы"""
    manager = get_service_manager()
    results = {}
    for service in ["vllm"]:  # Только внешние сервисы
        results[service] = await manager.start_service(service)
    return {"status": "ok", "results": results}


@app.post("/admin/services/stop-all")
async def admin_stop_all_services():
    """Остановить все внешние сервисы"""
    manager = get_service_manager()
    results = {}
    for service in ["vllm"]:
        results[service] = await manager.stop_service(service)
    return {"status": "ok", "results": results}


# ============== Logs Endpoints ==============


@app.get("/admin/logs")
async def admin_list_logs():
    """Список доступных логов"""
    manager = get_service_manager()
    return {"logs": manager.get_available_logs()}


@app.get("/admin/logs/{logfile}")
async def admin_read_log(
    logfile: str, lines: int = 100, offset: int = 0, search: Optional[str] = None
):
    """Прочитать лог файл"""
    manager = get_service_manager()
    return manager.read_log(logfile, lines=lines, offset=offset, search=search)


@app.get("/admin/logs/stream/{logfile}")
async def admin_stream_log(
    logfile: str,
    user: User = Depends(require_permission("system", "view")),
):
    """SSE streaming логов"""
    manager = get_service_manager()

    async def generate():
        async for data in manager.stream_log(logfile):
            yield f"data: {data}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ============== LLM Enhanced Endpoints ==============


@app.get("/admin/llm/backend")
async def admin_get_llm_backend():
    """Получить текущий LLM backend"""
    if llm_service:
        # Detect backend type
        if isinstance(llm_service, CloudLLMService):
            backend = f"cloud:{llm_service.provider_id}"
        elif hasattr(llm_service, "api_url"):
            backend = "vllm"
        else:
            backend = "unknown"

        return {
            "backend": backend,
            "model": getattr(llm_service, "model_name", "unknown"),
            "api_url": getattr(llm_service, "api_url", None),
            "provider_type": getattr(llm_service, "provider_type", None),
        }
    return {"backend": "none", "error": "LLM service not initialized"}


@app.get("/admin/llm/models")
async def admin_get_llm_models():
    """
    Получить список доступных моделей vLLM и текущую модель.
    Возвращает информацию о Qwen, Llama, DeepSeek и других моделях.
    """
    from vllm_llm_service import AVAILABLE_MODELS

    result = {
        "available_models": AVAILABLE_MODELS,
        "current_model": None,
        "loaded_models": [],
        "backend": "none",
    }

    if llm_service:
        if isinstance(llm_service, CloudLLMService):
            result["backend"] = f"cloud:{llm_service.provider_id}"
            result["current_model"] = {
                "id": llm_service.provider_id,
                "name": getattr(llm_service, "model_name", "unknown"),
                "description": f"Cloud: {getattr(llm_service, 'provider_type', 'unknown')}",
                "available": True,
            }
        elif hasattr(llm_service, "api_url"):
            result["backend"] = "vllm"
            if hasattr(llm_service, "get_current_model_info"):
                result["current_model"] = llm_service.get_current_model_info()
                result["loaded_models"] = llm_service.get_loaded_models()

    return result


@app.post("/admin/llm/backend")
async def admin_set_llm_backend(
    request: AdminBackendRequest, user: User = Depends(get_current_user)
):
    """Переключить LLM backend с горячей перезагрузкой сервиса"""
    global LLM_BACKEND, llm_service

    # Auto-convert "gemini" to default cloud Gemini provider
    if request.backend == "gemini":
        gemini_provider = await _get_or_create_default_gemini_provider()
        if gemini_provider:
            return await _switch_to_cloud_provider(gemini_provider["id"], request.stop_unused, user)
        raise HTTPException(
            status_code=400,
            detail="Cannot switch to Gemini: no GEMINI_API_KEY configured. "
            "Create a Gemini cloud provider first.",
        )

    # Check if it's a cloud provider
    if request.backend.startswith("cloud:"):
        provider_id = request.backend.split(":", 1)[1]
        return await _switch_to_cloud_provider(provider_id, request.stop_unused, user)

    if request.backend != "vllm":
        raise HTTPException(
            status_code=400,
            detail="Invalid backend. Use 'vllm' or 'cloud:{provider_id}'",
        )

    # Проверяем текущий бэкенд
    current_backend = (
        "vllm"
        if (
            llm_service
            and hasattr(llm_service, "api_url")
            and not isinstance(llm_service, CloudLLMService)
        )
        else "cloud"
    )
    if request.backend == current_backend:
        return {
            "status": "ok",
            "backend": request.backend,
            "message": f"Уже используется {request.backend}",
        }

    manager = get_service_manager()

    try:
        if request.backend == "vllm":
            # Переключение на vLLM
            logger.info("🔄 Переключение на vLLM...")

            # Проверяем, запущен ли vLLM
            vllm_status = manager.get_service_status("vllm")

            if not vllm_status.get("is_running"):
                # Запускаем vLLM
                logger.info("🚀 Запуск vLLM...")
                start_result = await manager.start_service("vllm")
                if start_result.get("status") != "ok":
                    raise HTTPException(
                        status_code=503,
                        detail=f"Не удалось запустить vLLM: {start_result.get('message', 'Unknown error')}",
                    )

                # Ждём готовности vLLM (до 120 секунд)
                logger.info("⏳ Ожидание готовности vLLM...")
                import httpx

                # Нормализуем URL (удаляем trailing /v1)
                vllm_url = os.getenv("VLLM_API_URL", "http://localhost:11434").rstrip("/")
                if vllm_url.endswith("/v1"):
                    vllm_url = vllm_url[:-3]

                for i in range(60):  # 60 * 2 = 120 секунд
                    await asyncio.sleep(2)
                    try:
                        async with httpx.AsyncClient() as client:
                            resp = await client.get(f"{vllm_url}/v1/models", timeout=5.0)
                            if resp.status_code == 200:
                                logger.info(f"✅ vLLM готов (попытка {i + 1})")
                                break
                    except Exception:
                        pass
                else:
                    raise HTTPException(
                        status_code=503, detail=f"vLLM не стал доступен за 120 секунд ({vllm_url})"
                    )

            # Создаём новый vLLM сервис
            if VLLMLLMService is None:
                raise HTTPException(status_code=503, detail="VLLMLLMService не доступен")

            new_service = VLLMLLMService()
            if not new_service.is_available():
                raise HTTPException(status_code=503, detail="vLLM запущен, но не отвечает на API")

            llm_service = new_service
            LLM_BACKEND = "vllm"
            os.environ["LLM_BACKEND"] = "vllm"

            logger.info("✅ Переключено на vLLM")

            # Audit log
            await async_audit_logger.log(
                action="update",
                resource="config",
                resource_id="llm_backend",
                user_id=user.username,
                details={"backend": "vllm", "model": getattr(llm_service, "model_name", "unknown")},
            )

            return {
                "status": "ok",
                "backend": "vllm",
                "model": getattr(llm_service, "model_name", "unknown"),
                "message": "Переключено на vLLM",
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка переключения бэкенда: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _switch_to_cloud_provider(provider_id: str, stop_unused: bool, user: User):
    """Helper function to switch to a cloud provider"""
    global LLM_BACKEND, llm_service

    provider_config = await async_cloud_provider_manager.get_provider_with_key(provider_id)
    if not provider_config:
        raise HTTPException(status_code=404, detail=f"Provider {provider_id} not found")

    if not provider_config.get("enabled"):
        raise HTTPException(status_code=400, detail=f"Provider {provider_id} is disabled")

    if not provider_config.get("api_key"):
        raise HTTPException(
            status_code=400, detail=f"Provider {provider_id} has no API key configured"
        )

    try:
        new_service = CloudLLMService(provider_config)
        if not new_service.is_available():
            raise HTTPException(status_code=503, detail=f"Provider {provider_id} is not responding")

        llm_service = new_service
        LLM_BACKEND = f"cloud:{provider_id}"
        os.environ["LLM_BACKEND"] = LLM_BACKEND

        # Optionally stop vLLM to free GPU
        if stop_unused:
            manager = get_service_manager()
            vllm_status = manager.get_service_status("vllm")
            if vllm_status.get("is_running"):
                logger.info("🛑 Stopping vLLM to free GPU memory...")
                await manager.stop_service("vllm")

        logger.info(f"✅ Switched to cloud provider: {provider_config.get('name')}")

        # Audit log
        await async_audit_logger.log(
            action="update",
            resource="config",
            resource_id="llm_backend",
            user_id=user.username,
            details={
                "backend": f"cloud:{provider_id}",
                "provider_type": provider_config.get("provider_type"),
                "model": provider_config.get("model_name"),
            },
        )

        return {
            "status": "ok",
            "backend": f"cloud:{provider_id}",
            "provider_id": provider_id,
            "provider_type": provider_config.get("provider_type"),
            "model": provider_config.get("model_name"),
            "message": f"Switched to cloud provider: {provider_config.get('name')}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error switching to cloud provider: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Cloud LLM Providers API ==============


@app.get("/admin/llm/providers")
async def admin_list_cloud_providers(enabled_only: bool = False):
    """List all cloud LLM providers"""
    providers = await async_cloud_provider_manager.list_providers(enabled_only)
    return {
        "providers": providers,
        "provider_types": PROVIDER_TYPES,
    }


@app.get("/admin/llm/providers/{provider_id}")
async def admin_get_cloud_provider(
    provider_id: str, include_key: bool = False, user: User = Depends(get_current_user)
):
    """Get cloud provider by ID"""
    if include_key:
        provider = await async_cloud_provider_manager.get_provider_with_key(provider_id)
    else:
        provider = await async_cloud_provider_manager.get_provider(provider_id)

    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"provider": provider}


@app.post("/admin/llm/providers")
async def admin_create_cloud_provider(
    data: CloudProviderCreate, user: User = Depends(get_current_user)
):
    """Create new cloud LLM provider"""
    try:
        provider = await async_cloud_provider_manager.create_provider(
            name=data.name,
            provider_type=data.provider_type,
            api_key=data.api_key,
            base_url=data.base_url,
            model_name=data.model_name,
            enabled=data.enabled,
            is_default=data.is_default,
            config=data.config,
            description=data.description,
        )

        # Audit log
        await async_audit_logger.log(
            action="create",
            resource="cloud_provider",
            resource_id=provider["id"],
            user_id=user.username,
            details={"name": data.name, "provider_type": data.provider_type},
        )

        return {"status": "ok", "provider": provider}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/admin/llm/providers/{provider_id}")
async def admin_update_cloud_provider(
    provider_id: str, data: CloudProviderUpdate, user: User = Depends(get_current_user)
):
    """Update cloud LLM provider"""
    # Filter out None values
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}

    provider = await async_cloud_provider_manager.update_provider(provider_id, **update_data)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Audit log
    await async_audit_logger.log(
        action="update",
        resource="cloud_provider",
        resource_id=provider_id,
        user_id=user.username,
        details=update_data,
    )

    return {"status": "ok", "provider": provider}


@app.delete("/admin/llm/providers/{provider_id}")
async def admin_delete_cloud_provider(provider_id: str, user: User = Depends(get_current_user)):
    """Delete cloud LLM provider"""
    if not await async_cloud_provider_manager.delete_provider(provider_id):
        raise HTTPException(status_code=404, detail="Provider not found")

    # Audit log
    await async_audit_logger.log(
        action="delete",
        resource="cloud_provider",
        resource_id=provider_id,
        user_id=user.username,
    )

    return {"status": "ok", "message": f"Provider {provider_id} deleted"}


@app.post("/admin/llm/providers/{provider_id}/test")
async def admin_test_cloud_provider(provider_id: str, user: User = Depends(get_current_user)):
    """Test cloud provider connection"""
    provider_config = await async_cloud_provider_manager.get_provider_with_key(provider_id)
    if not provider_config:
        raise HTTPException(status_code=404, detail="Provider not found")

    if not provider_config.get("api_key"):
        return {
            "status": "error",
            "available": False,
            "message": "No API key configured",
        }

    try:
        service = CloudLLMService(provider_config)
        is_available = service.is_available()

        if is_available:
            # Quick test generation
            test_response = service.generate_response("Скажи 'тест ок'", use_history=False)
            return {
                "status": "ok",
                "available": True,
                "test_response": test_response[:200] if test_response else "",
            }
        else:
            return {
                "status": "error",
                "available": False,
                "message": "Provider not responding",
            }
    except Exception as e:
        return {
            "status": "error",
            "available": False,
            "message": str(e),
        }


@app.post("/admin/llm/providers/{provider_id}/set-default")
async def admin_set_default_cloud_provider(
    provider_id: str, user: User = Depends(get_current_user)
):
    """Set cloud provider as default"""
    if not await async_cloud_provider_manager.set_default(provider_id):
        raise HTTPException(status_code=404, detail="Provider not found or disabled")

    await async_audit_logger.log(
        action="update",
        resource="cloud_provider",
        resource_id=provider_id,
        user_id=user.username,
        details={"is_default": True},
    )

    return {"status": "ok", "message": f"Provider {provider_id} set as default"}


@app.get("/admin/llm/personas")
async def admin_get_personas():
    """Получить список доступных персон"""
    if llm_service and hasattr(llm_service, "get_available_personas"):
        return {"personas": llm_service.get_available_personas()}

    # Fallback для Gemini LLM Service
    from vllm_llm_service import SECRETARY_PERSONAS

    return {
        "personas": {
            pid: {"name": p["name"], "full_name": p.get("full_name", p["name"])}
            for pid, p in SECRETARY_PERSONAS.items()
        }
    }


@app.get("/admin/llm/persona")
async def admin_get_current_persona():
    """Получить текущую персону"""
    if llm_service:
        persona_id = getattr(llm_service, "persona_id", "anna")
        persona = getattr(llm_service, "persona", {})
        return {
            "id": persona_id,
            "name": persona.get("name", "Unknown"),
        }
    return {"id": "none", "error": "LLM service not initialized"}


@app.post("/admin/llm/persona")
async def admin_set_persona(request: AdminPersonaRequest, user: User = Depends(get_current_user)):
    """Установить персону"""
    if llm_service and hasattr(llm_service, "set_persona"):
        success = llm_service.set_persona(request.persona)
        if success:
            # Audit log
            await async_audit_logger.log(
                action="update",
                resource="config",
                resource_id="llm_persona",
                user_id=user.username,
                details={"persona": request.persona},
            )
            return {"status": "ok", "persona": request.persona}
        raise HTTPException(status_code=400, detail=f"Persona not found: {request.persona}")
    raise HTTPException(status_code=503, detail="LLM service does not support personas")


@app.get("/admin/llm/params")
async def admin_get_llm_params():
    """Получить параметры генерации LLM"""
    if llm_service and hasattr(llm_service, "runtime_params"):
        return {"params": llm_service.runtime_params}

    # Возвращаем значения по умолчанию
    return {
        "params": {"temperature": 0.7, "max_tokens": 512, "top_p": 0.9, "repetition_penalty": 1.1}
    }


@app.post("/admin/llm/params")
async def admin_set_llm_params(request: AdminLLMParamsRequest):
    """Установить параметры генерации LLM"""
    if llm_service and hasattr(llm_service, "set_params"):
        params = {k: v for k, v in request.dict().items() if v is not None}
        llm_service.set_params(**params)
        return {"status": "ok", "params": llm_service.runtime_params}

    # Для vLLM сервиса без set_params - сохраняем в атрибуте
    if llm_service:
        if not hasattr(llm_service, "runtime_params"):
            llm_service.runtime_params = {}
        params = {k: v for k, v in request.dict().items() if v is not None}
        llm_service.runtime_params.update(params)
        return {"status": "ok", "params": llm_service.runtime_params}

    raise HTTPException(status_code=503, detail="LLM service not initialized")


@app.get("/admin/llm/prompt/{persona}")
async def admin_get_persona_prompt(persona: str):
    """Получить системный промпт для персоны"""
    try:
        from vllm_llm_service import SECRETARY_PERSONAS

        if persona in SECRETARY_PERSONAS:
            return {"persona": persona, "prompt": SECRETARY_PERSONAS[persona]["prompt"]}
        raise HTTPException(status_code=404, detail=f"Persona not found: {persona}")
    except ImportError:
        raise HTTPException(status_code=503, detail="vLLM service not available")


@app.post("/admin/llm/prompt/{persona}")
async def admin_set_persona_prompt(persona: str, request: AdminLLMPromptRequest):
    """Установить системный промпт для персоны"""
    try:
        from vllm_llm_service import SECRETARY_PERSONAS

        if persona not in SECRETARY_PERSONAS:
            raise HTTPException(status_code=404, detail=f"Persona not found: {persona}")

        # Обновляем промпт
        SECRETARY_PERSONAS[persona]["prompt"] = request.prompt

        # Если это текущая персона - обновляем в сервисе
        if llm_service and hasattr(llm_service, "persona_id") and llm_service.persona_id == persona:
            llm_service.system_prompt = request.prompt

        return {"status": "ok", "persona": persona}
    except ImportError:
        raise HTTPException(status_code=503, detail="vLLM service not available")


@app.post("/admin/llm/prompt/{persona}/reset")
async def admin_reset_persona_prompt(persona: str):
    """Сбросить системный промпт персоны на значение по умолчанию"""
    # TODO: Реализовать хранение оригинальных промптов
    raise HTTPException(status_code=501, detail="Not implemented yet")


# ============== Fine-tuning Endpoints ==============


@app.post("/admin/finetune/dataset/upload")
async def admin_upload_dataset(file: UploadFile = File(...)):
    """Загрузить датасет (Telegram export JSON)"""
    manager = get_finetune_manager()
    content = await file.read()
    return await manager.upload_dataset(content, file.filename)


class DatasetProcessRequest(BaseModel):
    owner_name: Optional[str] = None
    transcribe_voice: Optional[bool] = None
    min_dialog_messages: Optional[int] = None
    max_message_length: Optional[int] = None
    max_dialog_length: Optional[int] = None
    include_groups: Optional[bool] = None
    output_name: Optional[str] = None


@app.post("/admin/finetune/dataset/process")
async def admin_process_dataset(request: Optional[DatasetProcessRequest] = None):
    """Обработать загруженный датасет"""
    manager = get_finetune_manager()
    config = request.model_dump(exclude_none=True) if request else None
    return await manager.process_dataset(config)


@app.get("/admin/finetune/dataset/config")
async def admin_get_dataset_config():
    """Получить конфигурацию обработки датасета"""
    manager = get_finetune_manager()
    return {"config": manager.get_dataset_config()}


@app.post("/admin/finetune/dataset/config")
async def admin_set_dataset_config(request: DatasetProcessRequest):
    """Установить конфигурацию обработки датасета"""
    manager = get_finetune_manager()
    return manager.set_dataset_config(**request.model_dump(exclude_none=True))


@app.get("/admin/finetune/dataset/processing-status")
async def admin_get_processing_status():
    """Получить статус обработки датасета"""
    manager = get_finetune_manager()
    return {"status": manager.get_processing_status()}


@app.get("/admin/finetune/dataset/stats")
async def admin_get_dataset_stats():
    """Получить статистику датасета"""
    manager = get_finetune_manager()
    stats = manager.get_dataset_stats()
    return {
        "stats": {
            "total_sessions": stats.total_sessions,
            "total_messages": stats.total_messages,
            "total_tokens": stats.total_tokens,
            "avg_tokens_per_message": stats.avg_tokens_per_message,
            "file_path": stats.file_path,
            "file_size_mb": stats.file_size_mb,
            "modified": stats.modified,
        }
    }


@app.get("/admin/finetune/dataset/list")
async def admin_list_datasets():
    """Список доступных датасетов"""
    manager = get_finetune_manager()
    return {"datasets": manager.list_datasets()}


@app.post("/admin/finetune/dataset/augment")
async def admin_augment_dataset():
    """Аугментировать датасет"""
    manager = get_finetune_manager()
    return await manager.augment_dataset()


class GenerateProjectDatasetRequest(BaseModel):
    include_tz: bool = True
    include_faq: bool = True
    include_docs: bool = True
    include_escalation: bool = True
    include_code: bool = True  # Python код и Markdown документация
    github_repo_url: Optional[str] = None  # URL публичного GitHub/GitLab репозитория
    github_branch: str = "main"  # Ветка для клонирования
    output_name: str = "project_dataset"


@app.post("/admin/finetune/dataset/generate-project")
async def admin_generate_project_dataset(request: GenerateProjectDatasetRequest):
    """Генерировать датасет из проектных источников (ТЗ, FAQ, документация, эскалации, код, GitHub)"""
    manager = get_finetune_manager()
    return await manager.generate_project_dataset(
        include_tz=request.include_tz,
        include_faq=request.include_faq,
        include_docs=request.include_docs,
        include_escalation=request.include_escalation,
        include_code=request.include_code,
        github_repo_url=request.github_repo_url,
        github_branch=request.github_branch,
        output_name=request.output_name,
    )


@app.get("/admin/finetune/config")
async def admin_get_finetune_config():
    """Получить конфигурацию обучения"""
    manager = get_finetune_manager()
    config = manager.get_config()
    return {
        "config": {
            "base_model": config.base_model,
            "lora_rank": config.lora_rank,
            "lora_alpha": config.lora_alpha,
            "lora_dropout": config.lora_dropout,
            "batch_size": config.batch_size,
            "gradient_accumulation_steps": config.gradient_accumulation_steps,
            "learning_rate": config.learning_rate,
            "num_epochs": config.num_epochs,
            "warmup_ratio": config.warmup_ratio,
            "max_seq_length": config.max_seq_length,
            "output_dir": config.output_dir,
        },
        "presets": {
            name: {
                "lora_rank": p.lora_rank,
                "batch_size": p.batch_size,
                "num_epochs": p.num_epochs,
            }
            for name, p in manager.get_config_presets().items()
        },
    }


@app.post("/admin/finetune/config")
async def admin_set_finetune_config(request: AdminFinetuneConfigRequest):
    """Установить конфигурацию обучения"""
    manager = get_finetune_manager()
    config = manager.get_config()

    # Обновляем только переданные параметры
    if request.lora_rank is not None:
        config.lora_rank = request.lora_rank
    if request.lora_alpha is not None:
        config.lora_alpha = request.lora_alpha
    if request.batch_size is not None:
        config.batch_size = request.batch_size
    if request.gradient_accumulation_steps is not None:
        config.gradient_accumulation_steps = request.gradient_accumulation_steps
    if request.learning_rate is not None:
        config.learning_rate = request.learning_rate
    if request.num_epochs is not None:
        config.num_epochs = request.num_epochs
    if request.max_seq_length is not None:
        config.max_seq_length = request.max_seq_length
    if request.output_dir is not None:
        config.output_dir = request.output_dir

    return manager.set_config(config)


@app.post("/admin/finetune/train/start")
async def admin_start_training():
    """Запустить обучение"""
    manager = get_finetune_manager()
    return await manager.start_training()


@app.post("/admin/finetune/train/stop")
async def admin_stop_training():
    """Остановить обучение"""
    manager = get_finetune_manager()
    return await manager.stop_training()


@app.get("/admin/finetune/train/status")
async def admin_get_training_status():
    """Получить статус обучения"""
    manager = get_finetune_manager()
    status = manager.get_training_status()
    return {
        "status": {
            "is_running": status.is_running,
            "current_step": status.current_step,
            "total_steps": status.total_steps,
            "current_epoch": status.current_epoch,
            "total_epochs": status.total_epochs,
            "loss": status.loss,
            "learning_rate": status.learning_rate,
            "elapsed_seconds": status.elapsed_seconds,
            "eta_seconds": status.eta_seconds,
            "error": status.error,
        }
    }


@app.get("/admin/finetune/train/log")
async def admin_stream_training_log(
    user: User = Depends(require_permission("system", "view")),
):
    """SSE streaming лога обучения"""
    manager = get_finetune_manager()

    async def generate():
        async for data in manager.stream_training_log():
            yield f"data: {data}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.get("/admin/finetune/adapters")
async def admin_list_adapters():
    """Получить список LoRA адаптеров"""
    manager = get_finetune_manager()
    adapters = manager.list_adapters()
    return {
        "adapters": [
            {
                "name": a.name,
                "path": a.path,
                "size_mb": a.size_mb,
                "modified": a.modified,
                "active": a.active,
                "config": a.config,
            }
            for a in adapters
        ],
        "active": manager.active_adapter,
    }


@app.post("/admin/finetune/adapters/activate")
async def admin_activate_adapter(request: AdminAdapterRequest):
    """Активировать LoRA адаптер"""
    manager = get_finetune_manager()
    return await manager.activate_adapter(request.adapter)


@app.delete("/admin/finetune/adapters/{name}")
async def admin_delete_adapter(name: str):
    """Удалить LoRA адаптер"""
    manager = get_finetune_manager()
    return await manager.delete_adapter(name)


# ============== TTS Finetune Endpoints ==============


@app.get("/admin/tts-finetune/config")
async def admin_get_tts_finetune_config():
    """Получить конфигурацию TTS fine-tuning"""
    manager = get_tts_finetune_manager()
    return {"config": manager.get_config()}


@app.post("/admin/tts-finetune/config")
async def admin_set_tts_finetune_config(config: dict):
    """Обновить конфигурацию TTS fine-tuning"""
    manager = get_tts_finetune_manager()
    return {"status": "ok", "config": manager.set_config(config)}


@app.get("/admin/tts-finetune/samples")
async def admin_get_tts_samples():
    """Получить список образцов голоса"""
    manager = get_tts_finetune_manager()
    return {"samples": manager.get_samples()}


@app.post("/admin/tts-finetune/samples/upload")
async def admin_upload_tts_sample(file: UploadFile = File(...)):
    """Загрузить образец голоса"""
    manager = get_tts_finetune_manager()
    content = await file.read()
    sample = manager.add_sample(file.filename, content)
    return {
        "status": "ok",
        "sample": {
            "filename": sample.filename,
            "path": sample.path,
            "duration_sec": sample.duration_sec,
            "size_kb": sample.size_kb,
        },
    }


@app.delete("/admin/tts-finetune/samples/{filename}")
async def admin_delete_tts_sample(filename: str):
    """Удалить образец голоса"""
    manager = get_tts_finetune_manager()
    if manager.delete_sample(filename):
        return {"status": "ok", "message": f"Sample {filename} deleted"}
    raise HTTPException(status_code=404, detail="Sample not found")


@app.put("/admin/tts-finetune/samples/{filename}/transcript")
async def admin_update_tts_transcript(filename: str, request: dict):
    """Обновить транскрипцию образца"""
    manager = get_tts_finetune_manager()
    transcript = request.get("transcript", "")
    sample = manager.update_transcript(filename, transcript)
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    return {
        "status": "ok",
        "sample": {
            "filename": sample.filename,
            "transcript": sample.transcript,
            "transcript_edited": sample.transcript_edited,
        },
    }


@app.post("/admin/tts-finetune/transcribe")
async def admin_transcribe_tts_samples():
    """Запустить транскрибацию образцов через Whisper"""
    manager = get_tts_finetune_manager()
    if manager.transcribe_samples():
        return {"status": "ok", "message": "Transcription started"}
    return {"status": "error", "message": "Already running or no samples to transcribe"}


@app.post("/admin/tts-finetune/prepare")
async def admin_prepare_tts_dataset():
    """Подготовить датасет (извлечь audio_codes)"""
    manager = get_tts_finetune_manager()
    if manager.prepare_dataset():
        return {"status": "ok", "message": "Dataset preparation started"}
    return {"status": "error", "message": "Already running or no samples with transcripts"}


@app.get("/admin/tts-finetune/processing-status")
async def admin_get_tts_processing_status():
    """Получить статус обработки"""
    manager = get_tts_finetune_manager()
    return {"status": manager.get_processing_status()}


@app.post("/admin/tts-finetune/train/start")
async def admin_start_tts_training():
    """Запустить обучение TTS"""
    manager = get_tts_finetune_manager()
    if manager.start_training():
        return {"status": "ok", "message": "Training started"}
    return {"status": "error", "message": "Already running or dataset not prepared"}


@app.post("/admin/tts-finetune/train/stop")
async def admin_stop_tts_training():
    """Остановить обучение TTS"""
    manager = get_tts_finetune_manager()
    if manager.stop_training():
        return {"status": "ok", "message": "Training stopped"}
    return {"status": "error", "message": "Training not running"}


@app.get("/admin/tts-finetune/train/status")
async def admin_get_tts_training_status():
    """Получить статус обучения TTS"""
    manager = get_tts_finetune_manager()
    return {"status": manager.get_training_status()}


@app.get("/admin/tts-finetune/train/log")
async def admin_get_tts_training_log():
    """Получить лог обучения TTS"""
    manager = get_tts_finetune_manager()
    return {"log": manager.get_training_log()}


@app.get("/admin/tts-finetune/models")
async def admin_get_tts_trained_models():
    """Получить список обученных TTS моделей"""
    manager = get_tts_finetune_manager()
    return {"models": manager.get_trained_models()}


# ============== Monitoring Endpoints ==============


@app.get("/admin/monitor/gpu")
async def admin_get_gpu_stats():
    """Получить статистику GPU"""
    import torch

    if not torch.cuda.is_available():
        return {"available": False, "gpus": []}

    gpus = []
    for i in range(torch.cuda.device_count()):
        try:
            name = torch.cuda.get_device_name(i)
            props = torch.cuda.get_device_properties(i)
            total_memory = props.total_memory / (1024**3)
            allocated = torch.cuda.memory_allocated(i) / (1024**3)
            reserved = torch.cuda.memory_reserved(i) / (1024**3)

            # Пытаемся получить утилизацию через nvidia-smi
            utilization = None
            temperature = None
            try:
                import subprocess

                result = subprocess.run(
                    [
                        "nvidia-smi",
                        f"--id={i}",
                        "--query-gpu=utilization.gpu,temperature.gpu",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    parts = result.stdout.strip().split(",")
                    if len(parts) >= 2:
                        utilization = int(parts[0].strip())
                        temperature = int(parts[1].strip())
            except Exception:
                pass

            gpus.append(
                {
                    "id": i,
                    "name": name,
                    "total_memory_gb": round(total_memory, 2),
                    "allocated_gb": round(allocated, 2),
                    "reserved_gb": round(reserved, 2),
                    "free_gb": round(total_memory - reserved, 2),
                    "utilization_percent": utilization,
                    "temperature_c": temperature,
                    "compute_capability": f"{props.major}.{props.minor}",
                }
            )
        except Exception as e:
            logger.warning(f"Error getting GPU {i} stats: {e}")

    return {"available": True, "gpus": gpus}


@app.get("/admin/monitor/health")
async def admin_get_health():
    """Расширенная проверка здоровья всех компонентов"""
    manager = get_service_manager()
    health = {"timestamp": datetime.now().isoformat(), "overall": "healthy", "components": {}}

    # Orchestrator
    health["components"]["orchestrator"] = {"status": "healthy", "uptime": "running"}

    # LLM
    if llm_service:
        try:
            if isinstance(llm_service, CloudLLMService):
                health["components"]["llm"] = {
                    "status": "healthy",
                    "backend": f"cloud:{getattr(llm_service, 'provider_id', 'unknown')}",
                }
            elif hasattr(llm_service, "is_available") and llm_service.is_available():
                health["components"]["llm"] = {"status": "healthy", "backend": "vllm"}
            else:
                health["components"]["llm"] = {"status": "healthy", "backend": "unknown"}
        except Exception as e:
            health["components"]["llm"] = {"status": "unhealthy", "error": str(e)}
            health["overall"] = "degraded"
    else:
        health["components"]["llm"] = {"status": "unavailable"}
        health["overall"] = "degraded"

    # TTS
    if anna_voice_service or voice_service:
        health["components"]["tts_xtts"] = {"status": "healthy"}
    else:
        health["components"]["tts_xtts"] = {"status": "unavailable"}

    if piper_service:
        health["components"]["tts_piper"] = {"status": "healthy"}
    else:
        health["components"]["tts_piper"] = {"status": "unavailable"}

    # vLLM external process
    vllm_status = manager.get_service_status("vllm")
    if vllm_status["is_running"]:
        health["components"]["vllm_process"] = {"status": "healthy", "pid": vllm_status["pid"]}
    else:
        health["components"]["vllm_process"] = {"status": "stopped"}

    return health


@app.get("/admin/monitor/metrics")
async def admin_get_metrics():
    """Получить метрики системы"""
    import psutil

    metrics = {
        "timestamp": datetime.now().isoformat(),
        "system": {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
            "memory_used_gb": round(psutil.virtual_memory().used / (1024**3), 2),
            "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        },
        "streaming_tts": streaming_tts_manager.get_stats() if streaming_tts_manager else None,
    }

    # LLM метрики
    if llm_service:
        metrics["llm"] = {
            "history_length": len(getattr(llm_service, "conversation_history", [])),
            "faq_count": len(getattr(llm_service, "faq", {})),
        }

    return metrics


@app.get("/admin/monitor/errors")
async def admin_get_errors():
    """Получить последние ошибки"""
    manager = get_service_manager()
    return {"errors": manager.last_errors, "timestamp": datetime.now().isoformat()}


@app.post("/admin/monitor/metrics/reset")
async def admin_reset_metrics():
    """Сбросить метрики"""
    # Очищаем кэш TTS
    if streaming_tts_manager:
        with streaming_tts_manager._cache_lock:
            streaming_tts_manager._cache.clear()

    return {"status": "ok", "message": "Metrics reset"}


@app.get("/admin/monitor/system")
async def admin_get_system_status():
    """Полная информация о системе: GPU, CPU, RAM, диски, Docker, сеть"""
    monitor = get_system_monitor()
    return monitor.get_full_status()


# ============== Model Management API ==============


@app.get("/admin/models/list")
async def admin_list_models():
    """Список всех локальных моделей"""
    manager = get_model_manager()
    return {"models": manager.get_cached_models()}


@app.post("/admin/models/scan")
async def admin_scan_models(request: Request):
    """Запустить сканирование моделей"""
    data = await request.json() if request.headers.get("content-type") == "application/json" else {}
    include_system = data.get("include_system", False)

    manager = get_model_manager()
    if manager.scan_all_models(include_system=include_system):
        return {"status": "ok", "message": "Scan started"}
    else:
        return {"status": "error", "message": "Scan already in progress"}


@app.post("/admin/models/scan/cancel")
async def admin_cancel_scan():
    """Отменить сканирование"""
    manager = get_model_manager()
    manager.cancel_scan()
    return {"status": "ok", "message": "Scan cancelled"}


@app.get("/admin/models/scan/status")
async def admin_scan_status():
    """Статус сканирования"""
    manager = get_model_manager()
    return {"status": manager.get_scan_progress()}


@app.post("/admin/models/download")
async def admin_download_model(request: Request):
    """Скачать модель с HuggingFace"""
    data = await request.json()
    repo_id = data.get("repo_id")
    revision = data.get("revision", "main")

    if not repo_id:
        raise HTTPException(status_code=400, detail="repo_id required")

    manager = get_model_manager()
    if manager.download_model(repo_id, revision):
        return {"status": "ok", "message": f"Download started: {repo_id}"}
    else:
        return {"status": "error", "message": "Download already in progress"}


@app.post("/admin/models/download/cancel")
async def admin_cancel_download():
    """Отменить загрузку"""
    manager = get_model_manager()
    manager.cancel_download()
    return {"status": "ok", "message": "Download cancelled"}


@app.get("/admin/models/download/status")
async def admin_download_status():
    """Статус загрузки"""
    manager = get_model_manager()
    return {"status": manager.get_download_progress()}


@app.delete("/admin/models/delete")
async def admin_delete_model(path: str):
    """Удалить модель"""
    manager = get_model_manager()
    result = manager.delete_model(path)
    if result["status"] == "ok":
        return result
    else:
        raise HTTPException(status_code=400, detail=result.get("error", "Delete failed"))


@app.get("/admin/models/search")
async def admin_search_huggingface(query: str, limit: int = 20):
    """Поиск моделей на HuggingFace"""
    manager = get_model_manager()
    results = manager.search_huggingface(query, limit)
    return {"results": results}


@app.get("/admin/models/details/{repo_id:path}")
async def admin_get_model_details(repo_id: str):
    """Получить детали модели с HuggingFace"""
    manager = get_model_manager()
    details = manager.get_model_details(repo_id)
    if details:
        return {"details": details}
    else:
        raise HTTPException(status_code=404, detail="Model not found")


# Widget public endpoints moved to modules/channels/widget/router_public.py
from modules.channels.widget.router_public import router as widget_public_router  # noqa: E402


app.include_router(widget_public_router)


# ============== Static Files for Vue Admin ==============

DEV_MODE = os.getenv("DEV_MODE", "").lower() in ("1", "true", "yes")
VITE_DEV_URL = os.getenv("VITE_DEV_URL", "http://localhost:5173")

if DEV_MODE:
    # Dev mode: proxy to Vite dev server for hot reload
    import httpx

    @app.api_route("/admin/{path:path}", methods=["GET", "HEAD"])
    async def proxy_to_vite(path: str, request: Request):
        """Proxy static files to Vite dev server"""
        async with httpx.AsyncClient() as client:
            url = f"{VITE_DEV_URL}/admin/{path}"
            try:
                resp = await client.get(url, headers=dict(request.headers))
                return Response(
                    content=resp.content, status_code=resp.status_code, headers=dict(resp.headers)
                )
            except httpx.ConnectError:
                return Response(
                    content=b"Vite dev server not running. Start with: cd admin && npm run dev",
                    status_code=503,
                )

    @app.get("/admin")
    async def proxy_admin_root():
        """Redirect /admin to /admin/"""
        return RedirectResponse(url="/admin/")

    logger.info(f"🔧 DEV MODE: Proxying /admin/* to Vite at {VITE_DEV_URL}")
else:
    # Production: serve built Vue app
    admin_dist_path = Path(__file__).parent / "admin" / "dist"
    if admin_dist_path.exists():
        from fastapi.staticfiles import StaticFiles

        app.mount("/admin", StaticFiles(directory=str(admin_dist_path), html=True), name="admin")
        logger.info(f"📂 Vue admin mounted at /admin from {admin_dist_path}")


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    port = int(os.getenv("ORCHESTRATOR_PORT", 8002))
    logger.info(f"🎯 Запуск Orchestrator на порту {port}")
    uvicorn.run(
        "orchestrator:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
