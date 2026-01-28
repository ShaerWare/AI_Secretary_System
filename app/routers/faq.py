# app/routers/faq.py
"""FAQ management router - CRUD operations for FAQ entries."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_container
from auth_manager import User, get_current_user
from db.integration import async_audit_logger, async_faq_manager


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
        faq_dict = await async_faq_manager.get_all()
        llm_service.reload_faq(faq_dict)


@router.get("")
async def admin_get_faq():
    """Получить все FAQ записи"""
    faq = await async_faq_manager.get_all()
    return {"faq": faq}


@router.post("")
async def admin_add_faq(request: AdminFAQRequest, user: User = Depends(get_current_user)):
    """Добавить FAQ запись"""
    await async_faq_manager.add(request.trigger, request.response)

    # Audit log
    await async_audit_logger.log(
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
    trigger: str, request: AdminFAQRequest, user: User = Depends(get_current_user)
):
    """Обновить FAQ запись"""
    result = await async_faq_manager.update(trigger, request.trigger, request.response)
    if not result:
        raise HTTPException(status_code=404, detail="FAQ entry not found")

    # Audit log
    await async_audit_logger.log(
        action="update",
        resource="faq",
        resource_id=request.trigger,
        user_id=user.username,
        details={"old_trigger": trigger, "response": request.response[:100]},
    )

    await _reload_llm_faq()

    return {"status": "ok", "trigger": request.trigger}


@router.delete("/{trigger}")
async def admin_delete_faq(trigger: str, user: User = Depends(get_current_user)):
    """Удалить FAQ запись"""
    if not await async_faq_manager.delete(trigger):
        raise HTTPException(status_code=404, detail=f"Trigger not found: {trigger}")

    # Audit log
    await async_audit_logger.log(
        action="delete", resource="faq", resource_id=trigger, user_id=user.username
    )

    await _reload_llm_faq()

    return {"status": "ok", "deleted": trigger}


@router.post("/reload")
async def admin_reload_faq():
    """Перезагрузить FAQ из БД"""
    await _reload_llm_faq()
    container = get_container()
    llm_service = container.llm_service
    faq_count = len(llm_service.faq) if llm_service and hasattr(llm_service, "faq") else 0
    return {"status": "ok", "count": faq_count}


@router.post("/save")
async def admin_save_faq():
    """Сохранить FAQ (уже автоматически сохраняется)"""
    return {"status": "ok", "message": "FAQ is saved automatically on each change"}


@router.post("/test")
async def admin_test_faq(request: AdminFAQTestRequest):
    """Тестировать FAQ поиск"""
    container = get_container()
    llm_service = container.llm_service
    if llm_service and hasattr(llm_service, "_check_faq"):
        result = llm_service._check_faq(request.text)
        if result:
            return {"match": True, "response": result}
        return {"match": False, "response": None}
    raise HTTPException(status_code=503, detail="LLM service not initialized")
