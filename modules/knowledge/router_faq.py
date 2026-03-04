# app/routers/faq.py
"""FAQ management router - CRUD operations for FAQ entries."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_container
from auth_manager import User, require_permission, workspace_context
from modules.knowledge.service import faq_service
from modules.monitoring.service import audit_service


router = APIRouter(prefix="/admin/faq", tags=["faq"])


class AdminFAQRequest(BaseModel):
    trigger: str
    response: str


class AdminFAQTestRequest(BaseModel):
    text: str


async def _reload_llm_faq():
    """Загружает FAQ из БД и обновляет LLM сервис."""
    container = get_container()
    llm_service = container.llm_service
    if llm_service and hasattr(llm_service, "reload_faq"):
        faq_dict = await faq_service.get_all()
        llm_service.reload_faq(faq_dict)


@router.get("")
async def admin_get_faq(user: User = Depends(require_permission("faq", "view"))):
    """Получить все FAQ записи"""
    _owner_id, ws_id = workspace_context(user, "faq")
    faq = await faq_service.get_all(workspace_id=ws_id)
    return {"faq": faq}


@router.post("")
async def admin_add_faq(
    request: AdminFAQRequest, user: User = Depends(require_permission("faq", "edit"))
):
    """Добавить FAQ запись"""
    _owner_id, ws_id = workspace_context(user, "faq")
    await faq_service.add(request.trigger, request.response, workspace_id=ws_id)

    # Audit log
    await audit_service.log(
        action="create",
        resource="faq",
        resource_id=request.trigger,
        user_id=user.username,
        details={"response": request.response[:100]},
    )

    # Перезагружаем FAQ в LLM сервисе из БД
    await _reload_llm_faq()

    return {"status": "ok", "trigger": request.trigger}


@router.put("/{trigger}")
async def admin_update_faq(
    trigger: str, request: AdminFAQRequest, user: User = Depends(require_permission("faq", "edit"))
):
    """Обновить FAQ запись"""
    _owner_id, ws_id = workspace_context(user, "faq")
    result = await faq_service.update(
        trigger, request.trigger, request.response, workspace_id=ws_id
    )
    if not result:
        raise HTTPException(status_code=404, detail="FAQ entry not found")

    # Audit log
    await audit_service.log(
        action="update",
        resource="faq",
        resource_id=request.trigger,
        user_id=user.username,
        details={"old_trigger": trigger, "response": request.response[:100]},
    )

    await _reload_llm_faq()

    return {"status": "ok", "trigger": request.trigger}


@router.delete("/{trigger}")
async def admin_delete_faq(trigger: str, user: User = Depends(require_permission("faq", "edit"))):
    """Удалить FAQ запись"""
    _owner_id, ws_id = workspace_context(user, "faq")
    if not await faq_service.delete(trigger, workspace_id=ws_id):
        raise HTTPException(status_code=404, detail=f"Trigger not found: {trigger}")

    # Audit log
    await audit_service.log(
        action="delete", resource="faq", resource_id=trigger, user_id=user.username
    )

    await _reload_llm_faq()

    return {"status": "ok", "deleted": trigger}


@router.post("/reload")
async def admin_reload_faq(user: User = Depends(require_permission("faq", "edit"))):
    """Перезагрузить FAQ из БД"""
    await _reload_llm_faq()
    container = get_container()
    llm_service = container.llm_service
    faq_count = len(llm_service.faq) if llm_service and hasattr(llm_service, "faq") else 0
    return {"status": "ok", "count": faq_count}


@router.post("/save")
async def admin_save_faq(user: User = Depends(require_permission("faq", "edit"))):
    """Сохранить FAQ (уже автоматически сохраняется)"""
    return {"status": "ok", "message": "FAQ is saved automatically on each change"}


@router.post("/test")
async def admin_test_faq(
    request: AdminFAQTestRequest, user: User = Depends(require_permission("faq", "view"))
):
    """Тестировать FAQ поиск"""
    container = get_container()
    llm_service = container.llm_service
    if llm_service and hasattr(llm_service, "_check_faq"):
        result = llm_service._check_faq(request.text)
        if result:
            return {"match": True, "response": result}
        return {"match": False, "response": None}
    raise HTTPException(status_code=503, detail="LLM service not initialized")
