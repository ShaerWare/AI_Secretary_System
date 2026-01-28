# app/routers/llm.py
"""LLM configuration router - backend switching, personas, providers, params."""

import asyncio
import logging
import os
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_container
from auth_manager import User, get_current_user
from cloud_llm_service import PROVIDER_TYPES, CloudLLMService
from db.integration import async_audit_logger, async_cloud_provider_manager
from llm_service import LLMService
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
    backend: str  # "vllm", "gemini", or "cloud:{provider_id}"
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
    persona: str  # "gulya" or "lidia"


class AdminLLMParamsRequest(BaseModel):
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    repetition_penalty: Optional[float] = None


# ============== Helper Functions ==============


async def _switch_to_cloud_provider(provider_id: str, stop_unused: bool, user: User):
    """Helper function to switch to a cloud provider"""
    container = get_container()

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


# ============== Prompt Endpoints ==============


@router.get("/prompt")
async def admin_get_llm_prompt():
    """Получить текущий системный промпт LLM"""
    container = get_container()
    llm_service = container.llm_service
    if llm_service:
        persona = getattr(llm_service, "current_persona", None) or os.getenv(
            "SECRETARY_PERSONA", "gulya"
        )
        return {
            "prompt": llm_service.system_prompt,
            "model": llm_service.model_name,
            "persona": persona,
        }
    raise HTTPException(status_code=503, detail="LLM service not initialized")


@router.post("/prompt")
async def admin_set_llm_prompt(request: AdminLLMPromptRequest):
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
async def admin_get_llm_model():
    """Получить текущую модель LLM"""
    container = get_container()
    llm_service = container.llm_service
    if llm_service:
        return {"model": llm_service.model_name}
    raise HTTPException(status_code=503, detail="LLM service not initialized")


@router.post("/model")
async def admin_set_llm_model(request: AdminLLMModelRequest):
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
async def admin_clear_llm_history():
    """Очистить историю диалога LLM"""
    container = get_container()
    llm_service = container.llm_service
    if llm_service:
        count = len(llm_service.conversation_history)
        llm_service.reset_conversation()
        return {"status": "ok", "cleared_messages": count}
    raise HTTPException(status_code=503, detail="LLM service not initialized")


@router.get("/history")
async def admin_get_llm_history():
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
async def admin_get_llm_backend():
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
            backend = "gemini"

        return {
            "backend": backend,
            "model": getattr(llm_service, "model_name", "unknown"),
            "api_url": getattr(llm_service, "api_url", None),
            "provider_type": getattr(llm_service, "provider_type", None),
        }
    return {"backend": "none", "error": "LLM service not initialized"}


@router.get("/models")
async def admin_get_llm_models():
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
        is_vllm = hasattr(llm_service, "api_url")
        result["backend"] = "vllm" if is_vllm else "gemini"

        if is_vllm and hasattr(llm_service, "get_current_model_info"):
            result["current_model"] = llm_service.get_current_model_info()
            result["loaded_models"] = llm_service.get_loaded_models()
        elif not is_vllm:
            # Gemini backend
            result["current_model"] = {
                "id": "gemini",
                "name": getattr(llm_service, "model_name", "gemini-2.0-flash"),
                "description": "Google Gemini API",
                "available": True,
            }

    return result


@router.post("/backend")
async def admin_set_llm_backend(
    request: AdminBackendRequest, user: User = Depends(get_current_user)
):
    """Переключить LLM backend с горячей перезагрузкой сервиса"""
    container = get_container()

    # Check if it's a cloud provider
    if request.backend.startswith("cloud:"):
        provider_id = request.backend.split(":", 1)[1]
        return await _switch_to_cloud_provider(provider_id, request.stop_unused, user)

    if request.backend not in ["vllm", "gemini"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid backend. Use 'vllm', 'gemini', or 'cloud:{provider_id}'",
        )

    llm_service = container.llm_service
    current_backend = "vllm" if (llm_service and hasattr(llm_service, "api_url")) else "gemini"
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

                for i in range(60):  # 60 * 2 = 120 секунд
                    await asyncio.sleep(2)
                    try:
                        async with httpx.AsyncClient() as client:
                            resp = await client.get("http://localhost:11434/health", timeout=5.0)
                            if resp.status_code == 200:
                                logger.info(f"✅ vLLM готов (попытка {i + 1})")
                                break
                    except Exception:
                        pass
                else:
                    raise HTTPException(
                        status_code=503, detail="vLLM не стал доступен за 120 секунд"
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

            container.llm_service = new_service
            os.environ["LLM_BACKEND"] = "vllm"

            logger.info("✅ Переключено на vLLM")

            # Audit log
            await async_audit_logger.log(
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

        else:
            # Переключение на Gemini
            logger.info("🔄 Переключение на Gemini...")

            new_service = LLMService()
            container.llm_service = new_service
            os.environ["LLM_BACKEND"] = "gemini"

            # Опционально останавливаем vLLM для освобождения GPU
            if request.stop_unused:
                vllm_status = manager.get_service_status("vllm")
                if vllm_status.get("is_running"):
                    logger.info("🛑 Останавливаем vLLM для освобождения GPU...")
                    await manager.stop_service("vllm")

            logger.info("✅ Переключено на Gemini")

            # Audit log
            await async_audit_logger.log(
                action="update",
                resource="config",
                resource_id="llm_backend",
                user_id=user.username,
                details={
                    "backend": "gemini",
                    "model": getattr(new_service, "model_name", "unknown"),
                },
            )

            return {
                "status": "ok",
                "backend": "gemini",
                "model": getattr(new_service, "model_name", "unknown"),
                "message": "Переключено на Gemini"
                + (" (vLLM остановлен)" if request.stop_unused else ""),
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка переключения бэкенда: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Cloud Providers Endpoints ==============


@router.get("/providers")
async def admin_list_cloud_providers(enabled_only: bool = False):
    """List all cloud LLM providers"""
    providers = await async_cloud_provider_manager.list_providers(enabled_only)
    return {
        "providers": providers,
        "provider_types": PROVIDER_TYPES,
    }


@router.get("/providers/{provider_id}")
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


@router.post("/providers")
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


@router.put("/providers/{provider_id}")
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


@router.delete("/providers/{provider_id}")
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


@router.post("/providers/{provider_id}/test")
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


@router.post("/providers/{provider_id}/set-default")
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


# ============== Persona Endpoints ==============


@router.get("/personas")
async def admin_get_personas():
    """Получить список доступных персон"""
    container = get_container()
    llm_service = container.llm_service
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


@router.get("/persona")
async def admin_get_current_persona():
    """Получить текущую персону"""
    container = get_container()
    llm_service = container.llm_service
    if llm_service:
        persona_id = getattr(llm_service, "persona_id", "gulya")
        persona = getattr(llm_service, "persona", {})
        return {
            "id": persona_id,
            "name": persona.get("name", "Unknown"),
        }
    return {"id": "none", "error": "LLM service not initialized"}


@router.post("/persona")
async def admin_set_persona(request: AdminPersonaRequest, user: User = Depends(get_current_user)):
    """Установить персону"""
    container = get_container()
    llm_service = container.llm_service
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


# ============== Params Endpoints ==============


@router.get("/params")
async def admin_get_llm_params():
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
async def admin_set_llm_params(request: AdminLLMParamsRequest):
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
async def admin_get_persona_prompt(persona: str):
    """Получить системный промпт для персоны"""
    try:
        from vllm_llm_service import SECRETARY_PERSONAS

        if persona in SECRETARY_PERSONAS:
            return {"persona": persona, "prompt": SECRETARY_PERSONAS[persona]["prompt"]}
        raise HTTPException(status_code=404, detail=f"Persona not found: {persona}")
    except ImportError:
        raise HTTPException(status_code=503, detail="vLLM service not available")


@router.post("/prompt/{persona}")
async def admin_set_persona_prompt(persona: str, request: AdminLLMPromptRequest):
    """Установить системный промпт для персоны"""
    try:
        from vllm_llm_service import SECRETARY_PERSONAS

        if persona not in SECRETARY_PERSONAS:
            raise HTTPException(status_code=404, detail=f"Persona not found: {persona}")

        # Обновляем промпт
        SECRETARY_PERSONAS[persona]["prompt"] = request.prompt

        # Если это текущая персона - обновляем в сервисе
        container = get_container()
        llm_service = container.llm_service
        if llm_service and hasattr(llm_service, "persona_id") and llm_service.persona_id == persona:
            llm_service.system_prompt = request.prompt

        return {"status": "ok", "persona": persona}
    except ImportError:
        raise HTTPException(status_code=503, detail="vLLM service not available")


@router.post("/prompt/{persona}/reset")
async def admin_reset_persona_prompt(persona: str):
    """Сбросить системный промпт персоны на значение по умолчанию"""
    # TODO: Реализовать хранение оригинальных промптов
    raise HTTPException(status_code=501, detail="Not implemented yet")
