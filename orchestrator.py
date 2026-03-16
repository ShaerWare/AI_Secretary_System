#!/usr/bin/env python3
"""
FastAPI entry point — wiring only, all domain logic in modules/.

Service init in modules/*/startup.py, endpoints in modules/*/router*.py,
background tasks in modules/*/tasks.py, domain services in modules/*/service.py.
"""

import logging
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.cors_middleware import DynamicCORSMiddleware
from app.rate_limiter import limiter
from app.security_headers import SECURITY_HEADERS_ENABLED, SecurityHeadersMiddleware


# Deployment mode: "full" (default), "cloud" (no GPU/hardware), "local" (explicit full)
DEPLOYMENT_MODE = os.getenv("DEPLOYMENT_MODE", "full").lower()
if DEPLOYMENT_MODE not in ("full", "cloud", "local"):
    DEPLOYMENT_MODE = "full"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Secretary Orchestrator", version="1.0.0")

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
CORS_ORIGINS_RAW = os.getenv("CORS_ORIGINS", "*")
CORS_ORIGINS = (
    ["*"]
    if CORS_ORIGINS_RAW == "*"
    else [o.strip() for o in CORS_ORIGINS_RAW.split(",") if o.strip()]
)
app.add_middleware(DynamicCORSMiddleware, static_origins=CORS_ORIGINS)
app.add_middleware(SecurityHeadersMiddleware, enabled=SECURITY_HEADERS_ENABLED)

# --- Router registration ---
from app.routers import (  # noqa: E402
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
from modules.channels.widget.router_public import router as widget_public_router  # noqa: E402
from modules.compat.router import router as compat_router  # noqa: E402
from modules.core.router_health import router as health_router  # noqa: E402
from modules.monitoring.router_logs import router as logs_router  # noqa: E402


# Always-available routers (all deployment modes)
_ALWAYS_ROUTERS = [
    auth,
    audit,
    faq,
    llm,
    chat,
    telegram,
    whatsapp,
    usage,
    widget,
    mobile,
    bot_sales,
    github_webhook,
    yoomoney_webhook,
    legal,
    backup,
    wiki_rag,
    woocommerce,
    github_repos,
    claude_code,
    kanban,
    roles,
    workspace,
]
for _r in _ALWAYS_ROUTERS:
    app.include_router(_r.router)
app.include_router(amocrm.router)
app.include_router(amocrm.webhook_router)
app.include_router(health_router)
app.include_router(compat_router)
app.include_router(logs_router)
app.include_router(widget_public_router)

# Hardware/GPU routers — skip in cloud mode
if DEPLOYMENT_MODE != "cloud":
    app.include_router(services.router)
    app.include_router(monitor.router)
    app.include_router(gsm.router)
    if stt is not None:
        app.include_router(stt.router)
    if tts is not None:
        app.include_router(tts.router)
    from modules.llm.router_finetune import router as llm_finetune_router
    from modules.llm.router_models import router as models_router
    from modules.speech.router_finetune import router as tts_finetune_router
    from modules.speech.router_voices import router as voices_router

    app.include_router(llm_finetune_router)
    app.include_router(tts_finetune_router)
    app.include_router(voices_router)
    app.include_router(models_router)

# Task registry for background tasks
from modules.core.tasks import TaskRegistry  # noqa: E402


task_registry = TaskRegistry()

# Working directories
Path("./temp").mkdir(exist_ok=True)
Path("./calls_log").mkdir(exist_ok=True)


@app.on_event("startup")
async def startup_event():
    """Initialize all services via domain startup modules."""
    logger.info(f"🚀 Запуск AI Secretary Orchestrator (mode={DEPLOYMENT_MODE})")

    from app.dependencies import get_container
    from db.integration import init_database

    await init_database()

    from modules.core.startup import check_legacy_files, seed_default_workspace, seed_system_roles

    await seed_system_roles()
    await seed_default_workspace()

    try:
        # TTS/STT services
        from modules.speech.startup import (
            init_streaming_tts_manager,
            init_stt_service,
            init_tts_services,
        )

        tts_result = init_tts_services(DEPLOYMENT_MODE)
        stt_service = init_stt_service()
        streaming_tts_manager = init_streaming_tts_manager()

        # LLM service
        from modules.llm.startup import init_llm_service

        llm_backend = os.getenv("LLM_BACKEND", "vllm").lower()
        llm_service, llm_backend = await init_llm_service(llm_backend)
        os.environ["LLM_BACKEND"] = llm_backend

        # Populate service container
        container = get_container()
        container.voice_service = tts_result["voice_service"]
        container.anna_voice_service = tts_result["anna_voice_service"]
        container.piper_service = tts_result["piper_service"]
        container.openvoice_service = tts_result["openvoice_service"]
        container.current_voice_config = tts_result["current_voice_config"]
        container.stt_service = stt_service
        container.llm_service = llm_service
        container.streaming_tts_manager = streaming_tts_manager

        # Reload FAQ and voice presets from DB
        from modules.knowledge.startup import reload_llm_faq
        from modules.speech.startup import reload_voice_presets

        await reload_llm_faq(container)
        await reload_voice_presets(container)

        # GSM telephony (GPU/full mode only)
        from modules.telephony.startup import init_gsm_services

        await init_gsm_services(container, DEPLOYMENT_MODE)

        # Internet Monitor + LLM auto-switching
        from modules.core.startup import init_internet_monitor

        await init_internet_monitor(container, DEPLOYMENT_MODE)

        # Wiki RAG service
        from modules.knowledge.startup import init_wiki_rag

        await init_wiki_rag(container, DEPLOYMENT_MODE, task_registry)

        check_legacy_files()

        logger.info("✅ Service container populated for modular routers")

        # Auto-start bots and bridge
        from modules.channels.telegram.startup import auto_start_bots as auto_start_telegram
        from modules.channels.whatsapp.startup import auto_start_bots as auto_start_whatsapp
        from modules.llm.startup import auto_start_bridge

        await auto_start_telegram()
        await auto_start_whatsapp()
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
        task_registry.register("woocommerce-sync", woocommerce_daily_sync)

        await task_registry.start_all()
        logger.info("✅ Основные сервисы загружены успешно")

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("🛑 Shutting down AI Secretary Orchestrator")
    await task_registry.cancel_all()

    from modules.core.startup import graceful_shutdown

    await graceful_shutdown()

    from db.integration import shutdown_database

    await shutdown_database()
    logger.info("✅ Shutdown complete")


# --- Static Files for Vue Admin ---

DEV_MODE = os.getenv("DEV_MODE", "").lower() in ("1", "true", "yes")
VITE_DEV_URL = os.getenv("VITE_DEV_URL", "http://localhost:5173")

if DEV_MODE:
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
