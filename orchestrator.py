#!/usr/bin/env python3
"""
Главный оркестратор - координирует все сервисы
STT (Whisper) -> LLM (vLLM / Cloud) -> TTS (XTTS v2)
"""

import logging
import os
from functools import partial
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import (
    RedirectResponse,
    Response,
)
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

# Cloud LLM service for multi-provider support
from cloud_llm_service import CloudLLMService
from db.integration import (
    async_cloud_provider_manager,
    init_database,
    shutdown_database,
)


# Database integration


# Multi-bot manager
try:
    from piper_tts_service import PiperTTSService

    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False
    PiperTTSService = None


try:
    from stt_service import STTService

    STT_AVAILABLE = True
except ImportError:
    STT_AVAILABLE = False
    STTService = None


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

# Core health + legacy/compat endpoints (Phase 4.3)
from modules.compat.router import router as compat_router  # noqa: E402
from modules.core.router_health import router as health_router  # noqa: E402


app.include_router(health_router)
app.include_router(compat_router)

# Hardware/GPU routers — skip in cloud mode
if DEPLOYMENT_MODE != "cloud":
    app.include_router(services.router)
    app.include_router(monitor.router)
    app.include_router(gsm.router)
    if stt is not None:
        app.include_router(stt.router)
    if tts is not None:
        app.include_router(tts.router)
    # Finetune routers (Phase 4.4) — GPU-only
    from modules.llm.router_finetune import router as llm_finetune_router
    from modules.speech.router_finetune import router as tts_finetune_router

    app.include_router(llm_finetune_router)
    app.include_router(tts_finetune_router)
    # Voice + model management (Phase 4.5) — GPU-only
    from modules.llm.router_models import router as models_router
    from modules.speech.router_voices import router as voices_router

    app.include_router(voices_router)
    app.include_router(models_router)

# Logs router (available in all modes)
from modules.monitoring.router_logs import router as logs_router  # noqa: E402


app.include_router(logs_router)

# Widget public endpoints
from modules.channels.widget.router_public import router as widget_public_router  # noqa: E402


app.include_router(widget_public_router)

# Task registry for background tasks (session cleanup, vacuum, syncs)
from modules.core.tasks import TaskRegistry  # noqa: E402


task_registry = TaskRegistry()

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

    # Seed system roles and default workspace
    from modules.core.startup import seed_default_workspace, seed_system_roles

    await seed_system_roles()
    await seed_default_workspace()

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
        from modules.llm.startup import get_or_create_default_gemini_provider

        # Auto-migrate legacy "gemini" backend to cloud provider system
        if LLM_BACKEND == "gemini":
            logger.info("🔄 Auto-migrating LLM_BACKEND=gemini to cloud provider...")
            gemini_provider = await get_or_create_default_gemini_provider()
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
                    gemini_provider = await get_or_create_default_gemini_provider()
                    if gemini_provider:
                        llm_service = CloudLLMService(gemini_provider)
                        LLM_BACKEND = f"cloud:{gemini_provider['id']}"
                        os.environ["LLM_BACKEND"] = LLM_BACKEND
                        logger.info(f"✅ Fallback на cloud: {gemini_provider['id']}")
                    else:
                        logger.warning("⚠️ Нет облачного провайдера для fallback")
            except Exception as e:
                logger.warning(f"⚠️ vLLM недоступен ({e}), пробуем облачного провайдера...")
                gemini_provider = await get_or_create_default_gemini_provider()
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

        # Reload FAQ and voice presets from DB
        from modules.knowledge.startup import reload_llm_faq
        from modules.speech.startup import reload_voice_presets

        await reload_llm_faq(container)
        await reload_voice_presets(container)

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
                # Build embeddings in background (registered via TaskRegistry below)
                from modules.knowledge.tasks import build_wiki_embeddings

                task_registry.register("wiki-embeddings", partial(build_wiki_embeddings, wiki_rag))
            else:
                logger.info("📚 Wiki RAG: BM25 only (no embedding provider)")

            # Load per-collection indexes in background
            from modules.knowledge.tasks import load_collection_indexes

            task_registry.register(
                "wiki-collection-indexes", partial(load_collection_indexes, wiki_rag)
            )

        except Exception as wiki_err:
            logger.warning(f"⚠️ Wiki RAG service not available: {wiki_err}")

        logger.info("✅ Service container populated for modular routers")

        # Auto-start Telegram bots that were running before restart
        from modules.channels.telegram.startup import auto_start_bots as auto_start_telegram

        await auto_start_telegram()

        # Auto-start WhatsApp bots that were running before restart
        from modules.channels.whatsapp.startup import auto_start_bots as auto_start_whatsapp

        await auto_start_whatsapp()

        # Auto-start bridge if enabled claude_bridge provider exists
        from modules.llm.startup import auto_start_bridge

        await auto_start_bridge()

        # Register background tasks via TaskRegistry
        from modules.core.maintenance import cleanup_expired_sessions, periodic_vacuum
        from modules.ecommerce.tasks import woocommerce_daily_sync
        from modules.kanban.tasks import sync_kanban_issues

        task_registry.register("session-cleanup", cleanup_expired_sessions, interval=3600)
        task_registry.register(
            "periodic-vacuum", periodic_vacuum, interval=7 * 24 * 3600, initial_delay=24 * 3600
        )
        task_registry.register(
            "kanban-sync", sync_kanban_issues, interval=15 * 60, initial_delay=60
        )
        # WooCommerce: cron-style schedule (daily 23:00 UTC), manages own timing internally
        task_registry.register("woocommerce-sync", woocommerce_daily_sync)

        await task_registry.start_all()

        logger.info("✅ Основные сервисы загружены успешно")

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🛑 Shutting down AI Secretary Orchestrator")
    await task_registry.cancel_all()

    # Stop Telegram bots
    try:
        from multi_bot_manager import multi_bot_manager

        await multi_bot_manager.stop_all()
        logger.info("✅ Telegram bots stopped")
    except Exception as e:
        logger.warning(f"⚠️ Error stopping Telegram bots: {e}")

    # Stop WhatsApp bots
    try:
        from whatsapp_manager import whatsapp_manager

        await whatsapp_manager.stop_all()
        logger.info("✅ WhatsApp bots stopped")
    except Exception as e:
        logger.warning(f"⚠️ Error stopping WhatsApp bots: {e}")

    # Stop Claude bridge
    try:
        from bridge_manager import bridge_manager

        await bridge_manager.stop()
        logger.info("✅ Claude bridge stopped")
    except Exception as e:
        logger.warning(f"⚠️ Error stopping Claude bridge: {e}")

    await shutdown_database()
    logger.info("✅ Shutdown complete")


# ============== Admin Web Interface ==============
# Vue 3 admin panel served from /admin (see Static Files section below)


# Remaining admin endpoints extracted in Phase 4.5
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
