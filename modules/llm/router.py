# modules/llm/router.py
"""LLM configuration router - backend switching, personas, providers, params."""

import asyncio
import logging
import os
from pathlib import Path
from typing import Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_container
from auth_manager import User, require_permission, workspace_context
from cloud_llm_service import PROVIDER_TYPES, CloudLLMService, GeminiProvider
from modules.llm.service import cloud_provider_service
from modules.monitoring.service import audit_service
from service_manager import get_service_manager


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/llm", tags=["llm"])


# ============== Pydantic Models ==============


class AdminLLMPromptRequest(BaseModel):
    """Запрос на изменение системного промпта"""

    prompt: str


class AdminLLMModelRequest(BaseModel):
    """Запрос на изменение модели LLM"""

    model: str  # gemini-2.5-flash, gemini-2.5-pro


class AdminBackendRequest(BaseModel):
    backend: str  # "vllm" or "cloud:{provider_id}"
    stop_unused: bool = False  # Остановить неиспользуемый сервис для освобождения GPU


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


class ProxyTestRequest(BaseModel):
    """Request to test VLESS proxy connection"""

    vless_url: str


class LLMPresetCreate(BaseModel):
    """Create LLM preset"""

    id: str
    name: str
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 512
    top_p: float = 0.9
    repetition_penalty: float = 1.1


class LLMPresetUpdate(BaseModel):
    """Update LLM preset"""

    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    repetition_penalty: Optional[float] = None


class VLLMModelRequest(BaseModel):
    """Request to change vLLM model"""

    model: str  # Full model name, e.g., "Qwen/Qwen2.5-7B-Instruct-AWQ"


# ============== Helper Functions ==============


async def _switch_to_cloud_provider(provider_id: str, stop_unused: bool, user: User):
    """Helper function to switch to a cloud provider"""
    container = get_container()

    provider_config = await cloud_provider_service.get_provider_with_key(provider_id)
    if not provider_config:
        raise HTTPException(status_code=404, detail=f"Provider {provider_id} not found")

    if not provider_config.get("enabled"):
        raise HTTPException(status_code=400, detail=f"Provider {provider_id} is disabled")

    is_bridge = provider_config.get("provider_type") == "claude_bridge"

    # Bridge doesn't need API key (uses local claude CLI auth)
    if not is_bridge and not provider_config.get("api_key"):
        raise HTTPException(
            status_code=400, detail=f"Provider {provider_id} has no API key configured"
        )

    try:
        # Auto-start bridge if provider_type is claude_bridge
        if is_bridge:
            from bridge_manager import bridge_manager

            if not bridge_manager.is_running:
                config = provider_config.get("config") or {}
                port = config.get("bridge_port", 8787)
                permission = config.get("permission_level", "chat")
                result = await bridge_manager.start(port=port, permission_level=permission)
                if result.get("status") != "ok":
                    raise HTTPException(
                        status_code=503,
                        detail=f"Bridge failed to start: {result.get('error')}",
                    )

            # Override base_url to actual bridge URL
            provider_config["base_url"] = bridge_manager.get_base_url()
            # Bridge doesn't need API key — set dummy for OpenAICompatibleProvider
            if not provider_config.get("api_key"):
                provider_config["api_key"] = "bridge-local"

        new_service = CloudLLMService(provider_config)
        if not new_service.is_available():
            raise HTTPException(status_code=503, detail=f"Provider {provider_id} is not responding")

        # Stop bridge if switching away from claude_bridge
        current_service = container.llm_service
        if (
            current_service
            and getattr(current_service, "provider_type", None) == "claude_bridge"
            and not is_bridge
        ):
            from bridge_manager import bridge_manager

            if bridge_manager.is_running:
                logger.info("🛑 Stopping bridge (switching to another provider)...")
                await bridge_manager.stop()

        container.llm_service = new_service
        os.environ["LLM_BACKEND"] = f"cloud:{provider_id}"

        # Optionally stop vLLM to free GPU
        if stop_unused:
            manager = get_service_manager()
            vllm_status = manager.get_service_status("vllm")
            if vllm_status.get("is_running"):
                logger.info("🛑 Stopping vLLM to free GPU memory...")
                await manager.stop_service("vllm")

        logger.info(f"✅ Switched to cloud provider: {provider_config.get('name')}")

        # Audit log
        await audit_service.log(
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


# ============== Prompt Endpoints ==============


@router.get("/prompt")
async def admin_get_llm_prompt(user: User = Depends(require_permission("llm", "view"))):
    """Получить текущий системный промпт LLM"""
    container = get_container()
    llm_service = container.llm_service
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


@router.post("/prompt")
async def admin_set_llm_prompt(
    request: AdminLLMPromptRequest, user: User = Depends(require_permission("llm", "edit"))
):
    """Установить новый системный промпт LLM"""
    container = get_container()
    llm_service = container.llm_service
    if llm_service:
        llm_service.set_system_prompt(request.prompt)
        return {
            "status": "ok",
            "prompt": request.prompt[:100] + "..." if len(request.prompt) > 100 else request.prompt,
        }
    raise HTTPException(status_code=503, detail="LLM service not initialized")


# ============== Model Endpoints ==============


@router.get("/model")
async def admin_get_llm_model(user: User = Depends(require_permission("llm", "view"))):
    """Получить текущую модель LLM"""
    container = get_container()
    llm_service = container.llm_service
    if llm_service:
        return {"model": llm_service.model_name}
    raise HTTPException(status_code=503, detail="LLM service not initialized")


@router.post("/model")
async def admin_set_llm_model(
    request: AdminLLMModelRequest, user: User = Depends(require_permission("llm", "edit"))
):
    """Изменить модель LLM"""
    allowed_models = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]

    if request.model not in allowed_models:
        raise HTTPException(
            status_code=400,
            detail=f"Неизвестная модель: {request.model}. Доступные: {allowed_models}",
        )

    container = get_container()
    llm_service = container.llm_service
    if llm_service:
        try:
            llm_service.set_model(request.model)
            return {"status": "ok", "model": request.model}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    raise HTTPException(status_code=503, detail="LLM service not initialized")


# ============== History Endpoints ==============


@router.delete("/history")
async def admin_clear_llm_history(user: User = Depends(require_permission("llm", "edit"))):
    """Очистить историю диалога LLM"""
    container = get_container()
    llm_service = container.llm_service
    if llm_service:
        count = len(llm_service.conversation_history)
        llm_service.reset_conversation()
        return {"status": "ok", "cleared_messages": count}
    raise HTTPException(status_code=503, detail="LLM service not initialized")


@router.get("/history")
async def admin_get_llm_history(user: User = Depends(require_permission("llm", "view"))):
    """Получить историю диалога LLM"""
    container = get_container()
    llm_service = container.llm_service
    if llm_service:
        return {
            "history": llm_service.conversation_history,
            "count": len(llm_service.conversation_history),
        }
    raise HTTPException(status_code=503, detail="LLM service not initialized")


# ============== Backend Endpoints ==============


@router.get("/backend")
async def admin_get_llm_backend(user: User = Depends(require_permission("llm", "view"))):
    """Получить текущий LLM backend"""
    container = get_container()
    llm_service = container.llm_service
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


@router.get("/models")
async def admin_get_llm_models(user: User = Depends(require_permission("llm", "view"))):
    """
    Получить список доступных моделей vLLM и текущую модель.
    Возвращает информацию о Qwen, Llama, DeepSeek и других моделях.
    """
    from vllm_llm_service import AVAILABLE_MODELS

    container = get_container()
    llm_service = container.llm_service
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


@router.post("/backend")
async def admin_set_llm_backend(
    request: AdminBackendRequest, user: User = Depends(require_permission("llm", "edit"))
):
    """Переключить LLM backend с горячей перезагрузкой сервиса"""
    container = get_container()

    # NOTE: bridge is stopped AFTER successful switch (not before),
    # so if the target backend fails, bridge remains running.

    # Auto-convert "gemini" to default cloud Gemini provider
    if request.backend == "gemini":
        # Find default Gemini cloud provider
        providers = await cloud_provider_service.list_providers(enabled_only=False)
        gemini_provider = next((p for p in providers if p.get("provider_type") == "gemini"), None)
        if gemini_provider:
            return await _switch_to_cloud_provider(gemini_provider["id"], request.stop_unused, user)
        raise HTTPException(
            status_code=400,
            detail="Cannot switch to Gemini: no Gemini cloud provider configured. "
            "Create one in Cloud Providers first.",
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

    llm_service = container.llm_service

    # Определяем текущий бэкенд
    if llm_service and isinstance(llm_service, CloudLLMService):
        current_backend = f"cloud:{llm_service.provider_id}"
    elif llm_service and hasattr(llm_service, "api_url"):
        current_backend = "vllm"
    else:
        current_backend = "unknown"

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

            # Определяем URL для vLLM (нормализуем - удаляем trailing /v1)
            vllm_url = os.getenv("VLLM_API_URL", "http://localhost:11434").rstrip("/")
            if vllm_url.endswith("/v1"):
                vllm_url = vllm_url[:-3]
            is_docker = Path("/.dockerenv").exists() or os.getenv("DOCKER_CONTAINER") == "1"

            # Проверяем доступность vLLM
            async def check_vllm_health() -> bool:
                try:
                    # trust_env=False: иначе глобальный HTTP_PROXY (VLESS от Gemini)
                    # уводит запрос к localhost в прокси и health-check всегда падает
                    async with httpx.AsyncClient(trust_env=False) as client:
                        # vLLM использует /v1/models для проверки доступности
                        try:
                            resp = await client.get(f"{vllm_url}/v1/models", timeout=5.0)
                            if resp.status_code == 200:
                                return True
                        except Exception:
                            pass
                except Exception:
                    pass
                return False

            vllm_accessible = await check_vllm_health()

            if not vllm_accessible:
                # Пытаемся запустить vLLM (и в Docker, и локально)
                vllm_status = manager.get_service_status("vllm")

                if not vllm_status.get("is_running"):
                    logger.info("🚀 Запуск vLLM...")
                    start_result = await manager.start_service("vllm")
                    if start_result.get("status") != "ok":
                        raise HTTPException(
                            status_code=503,
                            detail=f"Не удалось запустить vLLM: {start_result.get('message', 'Unknown error')}",
                        )

                # Ждём готовности vLLM (до 180 секунд для Docker, т.к. загрузка модели)
                max_attempts = 90 if is_docker else 60  # 180 или 120 секунд
                logger.info(f"⏳ Ожидание готовности vLLM (до {max_attempts * 2} сек)...")

                for i in range(max_attempts):
                    await asyncio.sleep(2)
                    if await check_vllm_health():
                        logger.info(f"✅ vLLM готов (попытка {i + 1})")
                        break
                else:
                    raise HTTPException(
                        status_code=503,
                        detail=f"vLLM не стал доступен по адресу {vllm_url}. "
                        "Проверьте логи контейнера: docker logs ai-secretary-vllm",
                    )

            # Создаём новый vLLM сервис
            try:
                from vllm_llm_service import VLLMLLMService

                new_service = VLLMLLMService()
                if not new_service.is_available():
                    raise HTTPException(
                        status_code=503, detail="vLLM запущен, но не отвечает на API"
                    )
            except ImportError:
                raise HTTPException(status_code=503, detail="VLLMLLMService не доступен")

            # Stop bridge only after vLLM is confirmed working
            current_service = container.llm_service
            if (
                current_service
                and getattr(current_service, "provider_type", None) == "claude_bridge"
            ):
                from bridge_manager import bridge_manager

                if bridge_manager.is_running:
                    logger.info("🛑 Stopping bridge (switching to vLLM)...")
                    await bridge_manager.stop()

            container.llm_service = new_service
            os.environ["LLM_BACKEND"] = "vllm"

            logger.info("✅ Переключено на vLLM")

            # Audit log
            await audit_service.log(
                action="update",
                resource="config",
                resource_id="llm_backend",
                user_id=user.username,
                details={"backend": "vllm", "model": getattr(new_service, "model_name", "unknown")},
            )

            return {
                "status": "ok",
                "backend": "vllm",
                "model": getattr(new_service, "model_name", "unknown"),
                "message": "Переключено на vLLM",
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка переключения бэкенда: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== vLLM Model Selection ==============


@router.get("/vllm-model")
async def admin_get_vllm_model(user: User = Depends(require_permission("llm", "manage"))):
    """
    Получить текущую настроенную модель vLLM.
    Возвращает модель из БД или env var.
    """
    from db.database import get_session_context
    from db.repositories.config import ConfigRepository

    # Пробуем из БД
    try:
        async with get_session_context() as session:
            config_repo = ConfigRepository(session)
            llm_config = await config_repo.get_llm_config()
            db_model = llm_config.get("vllm_model")
    except Exception:
        db_model = None

    # Fallback на env var
    env_model = os.getenv("VLLM_MODEL", "Qwen/Qwen2.5-7B-Instruct-AWQ")

    return {
        "model": db_model or env_model,
        "source": "db" if db_model else "env",
        "env_model": env_model,
    }


@router.post("/vllm-model")
async def admin_set_vllm_model(
    request: VLLMModelRequest, user: User = Depends(require_permission("llm", "manage"))
):
    """
    Изменить модель vLLM и перезапустить контейнер.

    Модель сохраняется в БД и используется при следующих запусках.
    Контейнер vLLM удаляется и создаётся заново с новой моделью.

    Примеры моделей:
    - Qwen/Qwen2.5-7B-Instruct-AWQ (по умолчанию)
    - deepseek-ai/deepseek-llm-7b-chat
    - meta-llama/Llama-3.1-8B-Instruct
    """
    manager = get_service_manager()

    # Проверяем, что мы в Docker режиме
    is_docker = Path("/.dockerenv").exists() or os.getenv("DOCKER_CONTAINER") == "1"
    if not is_docker:
        raise HTTPException(
            status_code=400,
            detail="Переключение модели vLLM поддерживается только в Docker режиме",
        )

    logger.info(f"🔄 Запрос на смену модели vLLM: {request.model}")

    try:
        result = await manager.switch_vllm_model(request.model)

        if result.get("status") == "ok":
            # Audit log
            await audit_service.log(
                action="update",
                resource="config",
                resource_id="vllm_model",
                user_id=user.username,
                details={"model": request.model},
            )

            return {
                "status": "ok",
                "model": request.model,
                "message": f"Модель vLLM изменена на {request.model}. Загрузка займёт 2-3 минуты.",
                "container_id": result.get("container_id"),
            }
        else:
            raise HTTPException(
                status_code=500, detail=result.get("message", "Ошибка переключения")
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка смены модели vLLM: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Cloud Providers Endpoints ==============


@router.get("/providers")
async def admin_list_cloud_providers(
    enabled_only: bool = False, user: User = Depends(require_permission("llm", "view"))
):
    """List all cloud LLM providers"""
    owner_id, ws_id = workspace_context(user, "llm")
    providers = await cloud_provider_service.list_providers(
        enabled_only, owner_id=owner_id, workspace_id=ws_id
    )
    return {
        "providers": providers,
        "provider_types": PROVIDER_TYPES,
    }


@router.get("/providers/{provider_id}")
async def admin_get_cloud_provider(
    provider_id: str,
    include_key: bool = False,
    user: User = Depends(require_permission("llm", "view")),
):
    """Get cloud provider by ID"""
    owner_id, ws_id = workspace_context(user, "llm")
    if include_key:
        provider = await cloud_provider_service.get_provider_with_key(provider_id)
    else:
        provider = await cloud_provider_service.get_provider(
            provider_id, owner_id=owner_id, workspace_id=ws_id
        )

    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"provider": provider}


@router.post("/providers")
async def admin_create_cloud_provider(
    data: CloudProviderCreate, user: User = Depends(require_permission("llm", "edit"))
):
    """Create new cloud LLM provider"""
    owner_id, ws_id = workspace_context(user, "llm")
    try:
        provider = await cloud_provider_service.create_provider(
            name=data.name,
            provider_type=data.provider_type,
            api_key=data.api_key,
            base_url=data.base_url,
            model_name=data.model_name,
            enabled=data.enabled,
            is_default=data.is_default,
            config=data.config,
            description=data.description,
            owner_id=owner_id,
            workspace_id=ws_id,
        )

        # Audit log
        await audit_service.log(
            action="create",
            resource="cloud_provider",
            resource_id=provider["id"],
            user_id=user.username,
            details={"name": data.name, "provider_type": data.provider_type},
        )

        return {"status": "ok", "provider": provider}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/providers/{provider_id}")
async def admin_update_cloud_provider(
    provider_id: str,
    data: CloudProviderUpdate,
    user: User = Depends(require_permission("llm", "edit")),
):
    """Update cloud LLM provider"""
    # Verify ownership
    owner_id, ws_id = workspace_context(user, "llm")
    existing = await cloud_provider_service.get_provider(
        provider_id, owner_id=owner_id, workspace_id=ws_id
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Filter out None values
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}

    provider = await cloud_provider_service.update_provider(provider_id, **update_data)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Audit log
    await audit_service.log(
        action="update",
        resource="cloud_provider",
        resource_id=provider_id,
        user_id=user.username,
        details=update_data,
    )

    return {"status": "ok", "provider": provider}


@router.delete("/providers/{provider_id}")
async def admin_delete_cloud_provider(
    provider_id: str, user: User = Depends(require_permission("llm", "edit"))
):
    """Delete cloud LLM provider"""
    owner_id, ws_id = workspace_context(user, "llm")
    if not await cloud_provider_service.delete_provider(
        provider_id, owner_id=owner_id, workspace_id=ws_id
    ):
        raise HTTPException(status_code=404, detail="Provider not found")

    # Audit log
    await audit_service.log(
        action="delete",
        resource="cloud_provider",
        resource_id=provider_id,
        user_id=user.username,
    )

    return {"status": "ok", "message": f"Provider {provider_id} deleted"}


@router.post("/providers/{provider_id}/test")
async def admin_test_cloud_provider(
    provider_id: str, user: User = Depends(require_permission("llm", "edit"))
):
    """Test cloud provider connection"""
    # Verify ownership before testing
    owner_id, ws_id = workspace_context(user, "llm")
    if not await cloud_provider_service.get_provider(
        provider_id, owner_id=owner_id, workspace_id=ws_id
    ):
        raise HTTPException(status_code=404, detail="Provider not found")
    provider_config = await cloud_provider_service.get_provider_with_key(provider_id)
    if not provider_config:
        raise HTTPException(status_code=404, detail="Provider not found")

    is_bridge = provider_config.get("provider_type") == "claude_bridge"

    if not is_bridge and not provider_config.get("api_key"):
        return {
            "status": "error",
            "available": False,
            "message": "No API key configured",
        }

    # For bridge: ensure it's running and set URL
    if is_bridge:
        from bridge_manager import bridge_manager

        if not bridge_manager.is_running:
            return {
                "status": "error",
                "available": False,
                "message": "Bridge is not running. Start it first.",
            }
        provider_config["base_url"] = bridge_manager.get_base_url()
        if not provider_config.get("api_key"):
            provider_config["api_key"] = "bridge-local"

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


@router.post("/providers/{provider_id}/set-default")
async def admin_set_default_cloud_provider(
    provider_id: str, user: User = Depends(require_permission("llm", "edit"))
):
    """Set cloud provider as default"""
    # Verify ownership
    owner_id, ws_id = workspace_context(user, "llm")
    if not await cloud_provider_service.get_provider(
        provider_id, owner_id=owner_id, workspace_id=ws_id
    ):
        raise HTTPException(status_code=404, detail="Provider not found")

    if not await cloud_provider_service.set_default(provider_id):
        raise HTTPException(status_code=404, detail="Provider not found or disabled")

    await audit_service.log(
        action="update",
        resource="cloud_provider",
        resource_id=provider_id,
        user_id=user.username,
        details={"is_default": True},
    )

    return {"status": "ok", "message": f"Provider {provider_id} set as default"}


# ============== Persona Endpoints ==============


@router.get("/personas")
async def admin_get_personas(user: User = Depends(require_permission("llm", "view"))):
    """Получить список доступных персон (из БД)"""
    from db.database import get_session_context
    from db.repositories.llm_preset import LLMPresetRepository

    async with get_session_context() as session:
        repo = LLMPresetRepository(session)
        await repo.ensure_defaults()
        presets = await repo.get_all_enabled()
        return {
            "personas": {
                p.id: {"name": p.name, "full_name": p.name, "description": p.description}
                for p in presets
            }
        }


@router.get("/persona")
async def admin_get_current_persona(user: User = Depends(require_permission("llm", "view"))):
    """Получить текущую персону (из БД)"""
    from db.database import get_session_context
    from db.repositories.llm_preset import LLMPresetRepository

    container = get_container()
    llm_service = container.llm_service
    current_id = "anna"
    if llm_service and hasattr(llm_service, "persona_id"):
        current_id = llm_service.persona_id

    async with get_session_context() as session:
        repo = LLMPresetRepository(session)
        await repo.ensure_defaults()
        preset = await repo.get_by_id(current_id)
        if preset:
            return {"id": preset.id, "name": preset.name}

        # Fallback to default
        default = await repo.get_default()
        if default:
            return {"id": default.id, "name": default.name}

    return {"id": "none", "error": "No preset found"}


@router.post("/persona")
async def admin_set_persona(
    request: AdminPersonaRequest, user: User = Depends(require_permission("llm", "edit"))
):
    """Установить персону (из БД)"""
    from db.database import get_session_context
    from db.repositories.llm_preset import LLMPresetRepository

    async with get_session_context() as session:
        repo = LLMPresetRepository(session)
        preset = await repo.get_by_id(request.persona)
        if not preset:
            raise HTTPException(status_code=404, detail=f"Persona not found: {request.persona}")

        # Set as default in DB
        await repo.set_default(request.persona)

        # Update llm_service with DB data
        container = get_container()
        llm_service = container.llm_service
        if llm_service and hasattr(llm_service, "set_persona"):
            persona_data = {
                "name": preset.name,
                "description": preset.description,
                "system_prompt": preset.system_prompt,
                "temperature": preset.temperature,
                "max_tokens": preset.max_tokens,
                "top_p": preset.top_p,
                "repetition_penalty": preset.repetition_penalty,
            }
            llm_service.set_persona(request.persona, persona_data=persona_data)

        # Audit log
        await audit_service.log(
            action="update",
            resource="config",
            resource_id="llm_persona",
            user_id=user.username,
            details={"persona": request.persona},
        )
        return {"status": "ok", "persona": request.persona}


# ============== Params Endpoints ==============


@router.get("/params")
async def admin_get_llm_params(user: User = Depends(require_permission("llm", "view"))):
    """Получить параметры генерации LLM"""
    container = get_container()
    llm_service = container.llm_service
    if llm_service and hasattr(llm_service, "runtime_params"):
        return {"params": llm_service.runtime_params}

    # Возвращаем значения по умолчанию
    return {
        "params": {"temperature": 0.7, "max_tokens": 512, "top_p": 0.9, "repetition_penalty": 1.1}
    }


@router.post("/params")
async def admin_set_llm_params(
    request: AdminLLMParamsRequest, user: User = Depends(require_permission("llm", "edit"))
):
    """Установить параметры генерации LLM"""
    container = get_container()
    llm_service = container.llm_service
    if llm_service and hasattr(llm_service, "set_params"):
        params = {k: v for k, v in request.model_dump().items() if v is not None}
        llm_service.set_params(**params)
        return {"status": "ok", "params": llm_service.runtime_params}

    # Для vLLM сервиса без set_params - сохраняем в атрибуте
    if llm_service:
        if not hasattr(llm_service, "runtime_params"):
            llm_service.runtime_params = {}
        params = {k: v for k, v in request.model_dump().items() if v is not None}
        llm_service.runtime_params.update(params)
        return {"status": "ok", "params": llm_service.runtime_params}

    raise HTTPException(status_code=503, detail="LLM service not initialized")


# ============== Persona Prompt Endpoints ==============


@router.get("/prompt/{persona}")
async def admin_get_persona_prompt(
    persona: str, user: User = Depends(require_permission("llm", "view"))
):
    """Получить системный промпт для персоны (из БД)"""
    from db.database import get_session_context
    from db.repositories.llm_preset import LLMPresetRepository

    async with get_session_context() as session:
        repo = LLMPresetRepository(session)
        preset = await repo.get_by_id(persona)
        if not preset:
            raise HTTPException(status_code=404, detail=f"Persona not found: {persona}")
        return {"persona": persona, "prompt": preset.system_prompt or ""}


@router.post("/prompt/{persona}")
async def admin_set_persona_prompt(
    persona: str,
    request: AdminLLMPromptRequest,
    user: User = Depends(require_permission("llm", "edit")),
):
    """Установить системный промпт для персоны (в БД)"""
    from db.database import get_session_context
    from db.repositories.llm_preset import LLMPresetRepository

    async with get_session_context() as session:
        repo = LLMPresetRepository(session)
        preset = await repo.update_prompt(persona, request.prompt)
        if not preset:
            raise HTTPException(status_code=404, detail=f"Persona not found: {persona}")

        # Если это текущая персона - обновляем в сервисе
        container = get_container()
        llm_service = container.llm_service
        if llm_service and hasattr(llm_service, "persona_id") and llm_service.persona_id == persona:
            llm_service.system_prompt = request.prompt

        return {"status": "ok", "persona": persona}


@router.post("/prompt/{persona}/reset")
async def admin_reset_persona_prompt(
    persona: str, user: User = Depends(require_permission("llm", "edit"))
):
    """Сбросить системный промпт персоны на значение по умолчанию"""
    from db.database import get_session_context
    from db.models import DEFAULT_LLM_PRESETS
    from db.repositories.llm_preset import LLMPresetRepository

    # Ищем дефолтный промпт
    default_data = next((p for p in DEFAULT_LLM_PRESETS if p["id"] == persona), None)
    if not default_data:
        raise HTTPException(status_code=400, detail=f"No default prompt for persona: {persona}")

    async with get_session_context() as session:
        repo = LLMPresetRepository(session)
        preset = await repo.update_prompt(persona, default_data["system_prompt"])
        if not preset:
            raise HTTPException(status_code=404, detail=f"Persona not found: {persona}")

        # Обновляем в сервисе если текущая персона
        container = get_container()
        llm_service = container.llm_service
        if llm_service and hasattr(llm_service, "persona_id") and llm_service.persona_id == persona:
            llm_service.system_prompt = default_data["system_prompt"]

        await audit_service.log(
            action="reset",
            resource="llm_preset",
            resource_id=persona,
            user_id=user.username,
        )

        return {"status": "ok", "persona": persona, "prompt": default_data["system_prompt"]}


# ============== Bridge Endpoints ==============


@router.get("/bridge/status")
async def admin_get_bridge_status(user: User = Depends(require_permission("llm", "view"))):
    """Get CLI-OpenAI Bridge process status."""
    from bridge_manager import bridge_manager

    return bridge_manager.get_status()


@router.post("/bridge/start")
async def admin_start_bridge(user: User = Depends(require_permission("llm", "edit"))):
    """Manually start the CLI-OpenAI Bridge."""
    from bridge_manager import bridge_manager

    if bridge_manager.is_running:
        return {
            "status": "ok",
            "message": "Bridge is already running",
            **bridge_manager.get_status(),
        }

    result = await bridge_manager.start()
    if result.get("status") != "ok":
        raise HTTPException(
            status_code=503, detail=f"Bridge failed to start: {result.get('error')}"
        )

    await audit_service.log(
        action="create",
        resource="bridge",
        resource_id="bridge",
        user_id=user.username,
        details={"action": "start"},
    )

    return result


@router.post("/bridge/stop")
async def admin_stop_bridge(user: User = Depends(require_permission("llm", "edit"))):
    """Manually stop the CLI-OpenAI Bridge."""
    from bridge_manager import bridge_manager

    if not bridge_manager.is_running:
        return {"status": "ok", "message": "Bridge is not running"}

    result = await bridge_manager.stop()

    await audit_service.log(
        action="delete",
        resource="bridge",
        resource_id="bridge",
        user_id=user.username,
        details={"action": "stop"},
    )

    return result


# ============== VLESS Proxy Endpoints ==============


@router.get("/proxy/status")
async def admin_get_proxy_status(user: User = Depends(require_permission("llm", "view"))):
    """
    Get VLESS proxy status for current Gemini provider.

    Returns xray availability, running state, and configuration.
    """
    container = get_container()
    llm_service = container.llm_service

    # Check if using Gemini provider with proxy
    if isinstance(llm_service, CloudLLMService):
        provider = llm_service.provider
        if isinstance(provider, GeminiProvider):
            return {"status": "ok", "proxy": provider.get_proxy_status()}

    # Check if xray is available globally
    try:
        from xray_proxy_manager import get_proxy_manager

        manager = get_proxy_manager()
        return {
            "status": "ok",
            "proxy": {
                "xray_available": manager.is_xray_available(),
                "xray_path": manager._xray_path,
                "configured": False,
                "is_running": False,
            },
        }
    except ImportError:
        return {
            "status": "ok",
            "proxy": {
                "xray_available": False,
                "configured": False,
                "is_running": False,
            },
        }


@router.post("/proxy/test")
async def admin_test_proxy(
    request: ProxyTestRequest, user: User = Depends(require_permission("llm", "manage"))
):
    """
    Test VLESS proxy connection to Google Gemini API.

    Args:
        request: Contains vless_url to test

    Returns:
        Test result with success status and details
    """
    try:
        from xray_proxy_manager import XrayProxyManager, validate_vless_url
    except ImportError:
        raise HTTPException(status_code=503, detail="xray_proxy_manager module not available")

    # Validate URL first
    is_valid, error = validate_vless_url(request.vless_url)
    if not is_valid:
        return {
            "status": "error",
            "success": False,
            "error": f"Invalid VLESS URL: {error}",
        }

    # Create temporary proxy manager for testing
    manager = XrayProxyManager()
    if not manager.is_xray_available():
        return {
            "status": "error",
            "success": False,
            "error": "xray binary not found. Install xray-core first.",
        }

    if not manager.configure(request.vless_url):
        return {
            "status": "error",
            "success": False,
            "error": "Failed to configure VLESS proxy",
        }

    # Test connection
    result = manager.test_connection("https://generativelanguage.googleapis.com")

    # Stop the test proxy
    manager.stop()

    if result.get("success"):
        # Audit log
        await audit_service.log(
            action="test",
            resource="vless_proxy",
            user_id=user.username,
            details={"target": result.get("target"), "status_code": result.get("status_code")},
        )
        return {
            "status": "ok",
            "success": True,
            "message": f"Connection successful (HTTP {result.get('status_code')})",
            "details": result,
        }
    else:
        return {
            "status": "error",
            "success": False,
            "error": result.get("error", "Unknown error"),
        }


@router.get("/proxy/validate")
async def admin_validate_vless_url(
    vless_url: str, user: User = Depends(require_permission("llm", "manage"))
):
    """
    Validate a VLESS URL without testing the connection.

    Args:
        vless_url: VLESS URL to validate

    Returns:
        Validation result with parsed configuration if valid
    """
    try:
        from xray_proxy_manager import parse_vless_url, validate_vless_url
    except ImportError:
        raise HTTPException(status_code=503, detail="xray_proxy_manager module not available")

    is_valid, error = validate_vless_url(vless_url)
    if not is_valid:
        return {
            "valid": False,
            "error": error,
        }

    # Parse and return safe info (without exposing full UUID)
    try:
        config = parse_vless_url(vless_url)
        return {
            "valid": True,
            "config": {
                "server": f"{config.address}:{config.port}",
                "security": config.security,
                "transport": config.transport_type,
                "remark": config.remark,
            },
        }
    except Exception as e:
        return {
            "valid": False,
            "error": str(e),
        }


class ProxyTestMultipleRequest(BaseModel):
    """Request to test multiple VLESS proxy URLs"""

    vless_urls: list[str]


@router.post("/proxy/test-multiple")
async def admin_test_multiple_proxies(
    request: ProxyTestMultipleRequest, user: User = Depends(require_permission("llm", "manage"))
):
    """
    Test multiple VLESS proxy URLs.

    Args:
        request: Contains list of vless_urls to test

    Returns:
        Test results for each proxy
    """
    try:
        from xray_proxy_manager import XrayProxyManagerWithFallback
    except ImportError:
        raise HTTPException(status_code=503, detail="xray_proxy_manager module not available")

    manager = XrayProxyManagerWithFallback(socks_port=10818, http_port=10819)
    if not manager.is_xray_available():
        return {
            "status": "error",
            "error": "xray binary not found. Install xray-core first.",
            "results": [],
        }

    count = manager.configure_proxies(request.vless_urls)
    if count == 0:
        return {
            "status": "error",
            "error": "No valid VLESS URLs provided",
            "results": [],
        }

    # Test all proxies
    results = manager.test_all_proxies()
    manager.stop()

    # Audit log
    successful = sum(1 for r in results if r.get("success"))
    await audit_service.log(
        action="test",
        resource="vless_proxy_multiple",
        user_id=user.username,
        details={"total": len(results), "successful": successful},
    )

    return {
        "status": "ok",
        "total": len(results),
        "successful": successful,
        "results": results,
    }


@router.post("/proxy/reset")
async def admin_reset_proxies(user: User = Depends(require_permission("llm", "manage"))):
    """
    Reset all proxies to enabled state (for fallback mode).
    """
    container = get_container()
    llm_service = container.llm_service

    if isinstance(llm_service, CloudLLMService):
        provider = llm_service.provider
        if isinstance(provider, GeminiProvider):
            provider.reset_proxies()

            await audit_service.log(
                action="reset",
                resource="vless_proxy",
                user_id=user.username,
            )

            return {"status": "ok", "message": "All proxies reset to enabled"}

    return {"status": "error", "message": "No Gemini provider with proxy configured"}


@router.post("/proxy/switch-next")
async def admin_switch_to_next_proxy(user: User = Depends(require_permission("llm", "manage"))):
    """
    Manually switch to the next proxy in fallback chain.
    """
    container = get_container()
    llm_service = container.llm_service

    if isinstance(llm_service, CloudLLMService):
        provider = llm_service.provider
        if isinstance(provider, GeminiProvider):
            provider.mark_proxy_failed()
            status = provider.get_proxy_status()

            await audit_service.log(
                action="switch",
                resource="vless_proxy",
                user_id=user.username,
                details={"new_proxy": status.get("current_proxy")},
            )

            return {"status": "ok", "proxy": status}

    return {"status": "error", "message": "No Gemini provider with fallback proxy configured"}


# ============== LLM Presets Endpoints ==============


@router.get("/presets")
async def admin_get_llm_presets(user: User = Depends(require_permission("llm", "view"))):
    """Get all LLM presets"""
    from db.database import get_session_context
    from db.repositories.llm_preset import LLMPresetRepository

    async with get_session_context() as session:
        repo = LLMPresetRepository(session)
        # Ensure default presets exist
        await repo.ensure_defaults()
        presets = await repo.get_all_enabled()
        return {"presets": [p.to_dict() for p in presets]}


@router.get("/presets/{preset_id}")
async def admin_get_llm_preset(
    preset_id: str, user: User = Depends(require_permission("llm", "view"))
):
    """Get a specific LLM preset"""
    from db.database import get_session_context
    from db.repositories.llm_preset import LLMPresetRepository

    async with get_session_context() as session:
        repo = LLMPresetRepository(session)
        preset = await repo.get_by_id(preset_id)
        if not preset:
            raise HTTPException(status_code=404, detail=f"Preset not found: {preset_id}")
        return preset.to_dict()


@router.post("/presets")
async def admin_create_llm_preset(
    request: LLMPresetCreate, user: User = Depends(require_permission("llm", "edit"))
):
    """Create a new LLM preset"""
    from db.database import get_session_context
    from db.models import LLMPreset
    from db.repositories.llm_preset import LLMPresetRepository

    async with get_session_context() as session:
        repo = LLMPresetRepository(session)

        # Check if preset already exists
        existing = await repo.get_by_id(request.id)
        if existing:
            raise HTTPException(status_code=400, detail=f"Preset already exists: {request.id}")

        preset = LLMPreset(**request.model_dump())
        session.add(preset)
        await session.commit()
        await session.refresh(preset)

        await audit_service.log(
            action="create",
            resource="llm_preset",
            resource_id=preset.id,
            user_id=user.username,
            details={"name": preset.name},
        )

        return preset.to_dict()


@router.put("/presets/{preset_id}")
async def admin_update_llm_preset(
    preset_id: str,
    request: LLMPresetUpdate,
    user: User = Depends(require_permission("llm", "edit")),
):
    """Update an existing LLM preset"""
    from db.database import get_session_context
    from db.repositories.llm_preset import LLMPresetRepository

    async with get_session_context() as session:
        repo = LLMPresetRepository(session)
        preset = await repo.get_by_id(preset_id)
        if not preset:
            raise HTTPException(status_code=404, detail=f"Preset not found: {preset_id}")

        # Update fields
        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if value is not None:
                setattr(preset, field, value)

        await session.commit()
        await session.refresh(preset)

        # Update llm_service if this is the current preset
        container = get_container()
        llm_service = container.llm_service
        if (
            llm_service
            and hasattr(llm_service, "persona_id")
            and llm_service.persona_id == preset_id
        ):
            # Update runtime params
            if hasattr(llm_service, "runtime_params"):
                llm_service.runtime_params["temperature"] = preset.temperature
                llm_service.runtime_params["max_tokens"] = preset.max_tokens
                llm_service.runtime_params["top_p"] = preset.top_p
                llm_service.runtime_params["repetition_penalty"] = preset.repetition_penalty
            # Update system prompt
            if preset.system_prompt:
                llm_service.system_prompt = preset.system_prompt

        await audit_service.log(
            action="update",
            resource="llm_preset",
            resource_id=preset_id,
            user_id=user.username,
            details=update_data,
        )

        return preset.to_dict()


@router.delete("/presets/{preset_id}")
async def admin_delete_llm_preset(
    preset_id: str, user: User = Depends(require_permission("llm", "edit"))
):
    """Delete an LLM preset"""
    from db.database import get_session_context
    from db.repositories.llm_preset import LLMPresetRepository

    # Prevent deletion of default presets
    if preset_id in ["anna", "marina"]:
        raise HTTPException(status_code=400, detail="Cannot delete default presets")

    async with get_session_context() as session:
        repo = LLMPresetRepository(session)
        preset = await repo.get_by_id(preset_id)
        if not preset:
            raise HTTPException(status_code=404, detail=f"Preset not found: {preset_id}")

        await repo.delete(preset)

        await audit_service.log(
            action="delete",
            resource="llm_preset",
            resource_id=preset_id,
            user_id=user.username,
        )

        return {"status": "ok", "deleted": preset_id}


@router.post("/presets/{preset_id}/activate")
async def admin_activate_llm_preset(
    preset_id: str, user: User = Depends(require_permission("llm", "edit"))
):
    """
    Activate an LLM preset - load its parameters into the current vLLM service.
    Also sets it as the default preset.
    """
    from db.database import get_session_context
    from db.repositories.llm_preset import LLMPresetRepository

    async with get_session_context() as session:
        repo = LLMPresetRepository(session)
        preset = await repo.get_by_id(preset_id)
        if not preset:
            raise HTTPException(status_code=404, detail=f"Preset not found: {preset_id}")

        # Set as default
        await repo.set_default(preset_id)

        # Update llm_service
        container = get_container()
        llm_service = container.llm_service

        if llm_service and hasattr(llm_service, "runtime_params"):
            # Update runtime params
            llm_service.runtime_params["temperature"] = preset.temperature
            llm_service.runtime_params["max_tokens"] = preset.max_tokens
            llm_service.runtime_params["top_p"] = preset.top_p
            llm_service.runtime_params["repetition_penalty"] = preset.repetition_penalty

            # Update system prompt
            if preset.system_prompt and hasattr(llm_service, "system_prompt"):
                llm_service.system_prompt = preset.system_prompt

            # Update persona_id for tracking
            if hasattr(llm_service, "persona_id"):
                llm_service.persona_id = preset_id
            if hasattr(llm_service, "persona"):
                llm_service.persona = {
                    "name": preset.name,
                    "full_name": preset.name,
                    "description": preset.description or "",
                    "prompt": preset.system_prompt or "",
                }

            logger.info(f"✅ LLM Preset activated: {preset.name} ({preset_id})")

        await audit_service.log(
            action="activate",
            resource="llm_preset",
            resource_id=preset_id,
            user_id=user.username,
            details={"name": preset.name, "params": preset.get_params()},
        )

        return {
            "status": "ok",
            "preset": preset.to_dict(),
            "message": f"Preset '{preset.name}' activated",
        }


@router.get("/presets/current")
async def admin_get_current_preset(user: User = Depends(require_permission("llm", "view"))):
    """Get the currently active LLM preset"""
    from db.database import get_session_context
    from db.repositories.llm_preset import LLMPresetRepository

    container = get_container()
    llm_service = container.llm_service

    # Get current preset_id from llm_service
    current_id = "anna"  # Default
    if llm_service and hasattr(llm_service, "persona_id"):
        current_id = llm_service.persona_id

    async with get_session_context() as session:
        repo = LLMPresetRepository(session)
        await repo.ensure_defaults()
        preset = await repo.get_by_id(current_id)

        if preset:
            return {"current": preset.to_dict()}

        # Fallback to default
        default = await repo.get_default()
        if default:
            return {"current": default.to_dict()}

        return {"current": None, "error": "No preset found"}
