"""LLM domain startup: service init, provider auto-creation, bridge auto-start."""

import logging
import os
from typing import Any, Optional


logger = logging.getLogger(__name__)

# Optional vLLM import
try:
    from vllm_llm_service import VLLMLLMService

    VLLM_AVAILABLE = True
except ImportError:
    VLLM_AVAILABLE = False
    VLLMLLMService = None


async def get_or_create_default_gemini_provider() -> Optional[dict]:
    """Find existing default Gemini provider or auto-create from GEMINI_API_KEY env.

    Returns provider config dict or None if no API key available.
    """
    from db.integration import async_cloud_provider_manager

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


async def init_llm_service(llm_backend: str) -> tuple[Any, str]:
    """Initialize LLM service with fallback chain.

    Returns (llm_service, updated_llm_backend).
    """
    from cloud_llm_service import CloudLLMService
    from db.integration import async_cloud_provider_manager

    llm_service = None

    # Auto-migrate legacy "gemini" backend to cloud provider system
    if llm_backend == "gemini":
        logger.info("🔄 Auto-migrating LLM_BACKEND=gemini to cloud provider...")
        gemini_provider = await get_or_create_default_gemini_provider()
        if gemini_provider:
            llm_backend = f"cloud:{gemini_provider['id']}"
            os.environ["LLM_BACKEND"] = llm_backend
            logger.info(f"✅ Migrated to {llm_backend}")
        else:
            logger.warning("⚠️ Cannot auto-migrate gemini backend: no GEMINI_API_KEY")
            llm_backend = "vllm"

    if llm_backend == "vllm" and VLLM_AVAILABLE:
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
                    llm_backend = f"cloud:{gemini_provider['id']}"
                    os.environ["LLM_BACKEND"] = llm_backend
                    logger.info(f"✅ Fallback на cloud: {gemini_provider['id']}")
                else:
                    logger.warning("⚠️ Нет облачного провайдера для fallback")
        except Exception as e:
            logger.warning(f"⚠️ vLLM недоступен ({e}), пробуем облачного провайдера...")
            gemini_provider = await get_or_create_default_gemini_provider()
            if gemini_provider:
                llm_service = CloudLLMService(gemini_provider)
                llm_backend = f"cloud:{gemini_provider['id']}"
                os.environ["LLM_BACKEND"] = llm_backend
                logger.info(f"✅ Fallback на cloud: {gemini_provider['id']}")
            else:
                logger.warning("⚠️ Нет облачного провайдера для fallback")
                llm_service = None
    elif llm_backend.startswith("cloud:"):
        provider_id = llm_backend.split(":", 1)[1]
        logger.info(f"☁️ LLM backend: {llm_backend} (cloud provider)")
        try:
            provider_config = await async_cloud_provider_manager.get_provider_with_key(provider_id)
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
        logger.warning(f"⚠️ Unknown LLM_BACKEND={llm_backend}, trying vLLM...")
        if VLLM_AVAILABLE:
            try:
                llm_service = VLLMLLMService()
                if llm_service.is_available():
                    llm_backend = "vllm"
                    logger.info("✅ vLLM подключен (fallback)")
                else:
                    llm_service = None
            except Exception:
                llm_service = None
        else:
            llm_service = None

    return llm_service, llm_backend


def create_llm_switch_callback(container):
    """Create callback for InternetMonitor to switch LLM backend on connectivity change.

    Returns async function(ConnectivityStatus) -> str.
    The callback writes to container.llm_service and os.environ["LLM_BACKEND"].
    """
    from cloud_llm_service import CloudLLMService
    from db.integration import async_cloud_provider_manager

    async def switch_llm(status) -> str:
        from modules.core.events import ConnectivityStatus

        if status in (ConnectivityStatus.ONLINE, ConnectivityStatus.DEGRADED):
            # Try cloud provider: claude_bridge first, then default, then any enabled
            try:
                providers = await async_cloud_provider_manager.list_providers(enabled_only=True)
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
                    container.llm_service = new_svc
                    ptype = provider.get("provider_type", "cloud")
                    backend = f"cloud ({ptype}: {provider.get('name', '?')})"
                    os.environ["LLM_BACKEND"] = f"cloud:{provider['id']}"
                    return backend
            except Exception as e:
                logger.warning(f"Cloud LLM switch failed: {e}")
            # Fallback to vLLM even when online
            if VLLM_AVAILABLE:
                try:
                    new_svc = VLLMLLMService()
                    if new_svc.is_available():
                        container.llm_service = new_svc
                        os.environ["LLM_BACKEND"] = "vllm"
                        return "vllm (cloud unavailable)"
                except Exception:
                    pass
            return os.environ.get("LLM_BACKEND", "unknown")  # keep current
        else:
            # Offline — switch to local vLLM
            if VLLM_AVAILABLE:
                try:
                    new_svc = VLLMLLMService()
                    if new_svc.is_available():
                        container.llm_service = new_svc
                        os.environ["LLM_BACKEND"] = "vllm"
                        return "vllm (offline)"
                except Exception as e:
                    logger.error(f"vLLM fallback failed: {e}")
            return os.environ.get("LLM_BACKEND", "unknown")  # keep current

    return switch_llm


async def setup_llm_event_subscriptions(event_bus) -> None:
    """Register LLM-domain event handlers."""
    from modules.knowledge.events import KnowledgeUpdated

    async def on_knowledge_updated(event: KnowledgeUpdated) -> None:
        """Reload FAQ cache when FAQ entries change."""
        if event.kind != "faq":
            return

        from app.dependencies import get_container
        from modules.knowledge.service import faq_service

        container = get_container()
        llm_service = container.llm_service
        if llm_service and hasattr(llm_service, "reload_faq"):
            faq_dict = await faq_service.get_all()
            llm_service.reload_faq(faq_dict)
            logger.info("KnowledgeUpdated handled: FAQ cache reloaded (action=%s)", event.action)

    event_bus.subscribe(KnowledgeUpdated, on_knowledge_updated)
    logger.info("LLM event subscriptions registered (KnowledgeUpdated)")


async def auto_start_bridge() -> None:
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


async def bridge_health_check() -> None:
    """Periodic health check for bridge — auto-restart if crashed."""
    from bridge_manager import bridge_manager
    from db.integration import async_cloud_provider_manager

    try:
        bridge_providers = await async_cloud_provider_manager.get_by_type(
            "claude_bridge", enabled_only=True
        )
        if not bridge_providers:
            return

        if bridge_manager.is_running:
            return

        # Bridge should be running but isn't — restart it
        logger.warning("🌉 Bridge not running, auto-restarting...")
        result = await bridge_manager.start()
        if result.get("status") == "ok":
            logger.info(f"🌉 Bridge auto-restarted on port {result.get('port', 8787)}")
        else:
            logger.warning(f"🌉 Bridge auto-restart failed: {result.get('error', 'unknown')}")
    except Exception as e:
        logger.error(f"🌉 Bridge health check error: {e}")
