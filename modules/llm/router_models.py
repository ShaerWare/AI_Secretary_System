"""HuggingFace model management endpoints.

List, scan, download, delete, and search models.
GPU-only — not registered in cloud deployment mode.
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from model_manager import get_model_manager


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/models", tags=["models"])


@router.get("/list")
async def admin_list_models():
    """Список всех локальных моделей"""
    manager = get_model_manager()
    return {"models": manager.get_cached_models()}


@router.post("/scan")
async def admin_scan_models(request: Request):
    """Запустить сканирование моделей"""
    data = await request.json() if request.headers.get("content-type") == "application/json" else {}
    include_system = data.get("include_system", False)

    manager = get_model_manager()
    if manager.scan_all_models(include_system=include_system):
        return {"status": "ok", "message": "Scan started"}
    else:
        return {"status": "error", "message": "Scan already in progress"}


@router.post("/scan/cancel")
async def admin_cancel_scan():
    """Отменить сканирование"""
    manager = get_model_manager()
    manager.cancel_scan()
    return {"status": "ok", "message": "Scan cancelled"}


@router.get("/scan/status")
async def admin_scan_status():
    """Статус сканирования"""
    manager = get_model_manager()
    return {"status": manager.get_scan_progress()}


@router.post("/download")
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


@router.post("/download/cancel")
async def admin_cancel_download():
    """Отменить загрузку"""
    manager = get_model_manager()
    manager.cancel_download()
    return {"status": "ok", "message": "Download cancelled"}


@router.get("/download/status")
async def admin_download_status():
    """Статус загрузки"""
    manager = get_model_manager()
    return {"status": manager.get_download_progress()}


@router.delete("/delete")
async def admin_delete_model(path: str):
    """Удалить модель"""
    manager = get_model_manager()
    result = manager.delete_model(path)
    if result["status"] == "ok":
        return result
    else:
        raise HTTPException(status_code=400, detail=result.get("error", "Delete failed"))


@router.get("/search")
async def admin_search_huggingface(query: str, limit: int = 20):
    """Поиск моделей на HuggingFace"""
    manager = get_model_manager()
    results = manager.search_huggingface(query, limit)
    return {"results": results}


@router.get("/details/{repo_id:path}")
async def admin_get_model_details(repo_id: str):
    """Получить детали модели с HuggingFace"""
    manager = get_model_manager()
    details = manager.get_model_details(repo_id)
    if details:
        return {"details": details}
    else:
        raise HTTPException(status_code=404, detail="Model not found")
