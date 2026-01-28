# app/routers/services.py
"""Service management router - start, stop, restart services."""

from fastapi import APIRouter

from app.dependencies import get_container
from service_manager import get_service_manager


router = APIRouter(prefix="/admin/services", tags=["services"])


@router.get("/status")
async def admin_services_status():
    """Получить статус всех сервисов"""
    manager = get_service_manager()
    status = manager.get_all_status()

    # Добавляем статус внутренних сервисов из контейнера
    container = get_container()
    status["services"]["xtts_gulya"]["is_running"] = container.gulya_voice_service is not None
    status["services"]["xtts_lidia"]["is_running"] = container.voice_service is not None
    status["services"]["piper"]["is_running"] = container.piper_service is not None
    status["services"]["openvoice"]["is_running"] = container.openvoice_service is not None
    status["services"]["orchestrator"]["is_running"] = True

    return status


@router.post("/{service}/start")
async def admin_start_service(service: str):
    """Запустить сервис"""
    manager = get_service_manager()
    return await manager.start_service(service)


@router.post("/{service}/stop")
async def admin_stop_service(service: str):
    """Остановить сервис"""
    manager = get_service_manager()
    return await manager.stop_service(service)


@router.post("/{service}/restart")
async def admin_restart_service(service: str):
    """Перезапустить сервис"""
    manager = get_service_manager()
    return await manager.restart_service(service)


@router.post("/start-all")
async def admin_start_all_services():
    """Запустить все внешние сервисы"""
    manager = get_service_manager()
    results = {}
    for service in ["vllm"]:  # Только внешние сервисы
        results[service] = await manager.start_service(service)
    return {"status": "ok", "results": results}


@router.post("/stop-all")
async def admin_stop_all_services():
    """Остановить все внешние сервисы"""
    manager = get_service_manager()
    results = {}
    for service in ["vllm"]:
        results[service] = await manager.stop_service(service)
    return {"status": "ok", "results": results}
