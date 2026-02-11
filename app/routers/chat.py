# app/routers/chat.py
"""Chat session router - sessions CRUD, messages, streaming."""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.dependencies import get_container
from app.rate_limiter import RATE_LIMIT_CHAT, limiter
from auth_manager import User, get_current_user
from cloud_llm_service import CloudLLMService
from db.integration import (
    async_bot_instance_manager,
    async_chat_manager,
    async_cloud_provider_manager,
    async_widget_instance_manager,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/chat", tags=["chat"])


# ============== Pydantic Models ==============


class CreateSessionRequest(BaseModel):
    title: Optional[str] = None
    system_prompt: Optional[str] = None
    source: Optional[str] = None  # "admin", "telegram", "widget"
    source_id: Optional[str] = None  # identifier (e.g., "bot_id:user_id")


class BulkDeleteRequest(BaseModel):
    session_ids: list[str]


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
    widget_instance_id: Optional[str] = None


class EditMessageRequest(BaseModel):
    content: str


# ============== Sessions Endpoints ==============


@router.get("/sessions")
async def admin_list_chat_sessions(
    group_by: Optional[str] = None, user: User = Depends(get_current_user)
):
    """Список всех чат-сессий. group_by=source для группировки по источнику."""
    owner_id = None if user.role == "admin" else user.id
    if group_by == "source":
        grouped = await async_chat_manager.list_sessions_grouped(owner_id=owner_id)
        return {"sessions": grouped, "grouped": True}
    sessions = await async_chat_manager.list_sessions(owner_id=owner_id)
    return {"sessions": sessions}


@router.post("/sessions")
async def admin_create_chat_session(
    request: CreateSessionRequest, user: User = Depends(get_current_user)
):
    """Создать новую чат-сессию"""
    owner_id = None if user.role == "admin" else user.id

    # Auto-apply widget system_prompt if not explicitly provided
    system_prompt = request.system_prompt
    if request.source == "widget" and request.source_id and not system_prompt:
        widget = await async_widget_instance_manager.get_instance(request.source_id)
        if widget and widget.get("system_prompt"):
            system_prompt = widget["system_prompt"]

    session = await async_chat_manager.create_session(
        request.title,
        system_prompt,
        request.source,
        request.source_id,
        owner_id=owner_id,
    )
    return {"session": session}


@router.post("/sessions/bulk-delete")
async def admin_bulk_delete_sessions(
    request: BulkDeleteRequest, user: User = Depends(get_current_user)
):
    """Удалить несколько сессий сразу"""
    owner_id = None if user.role == "admin" else user.id
    count = await async_chat_manager.delete_sessions_bulk(request.session_ids, owner_id=owner_id)
    return {"status": "ok", "deleted": count}


@router.get("/sessions/{session_id}")
async def admin_get_chat_session(session_id: str, user: User = Depends(get_current_user)):
    """Получить чат-сессию"""
    owner_id = None if user.role == "admin" else user.id
    session = await async_chat_manager.get_session(session_id, owner_id=owner_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": session}


@router.put("/sessions/{session_id}")
async def admin_update_chat_session(
    session_id: str, request: UpdateSessionRequest, user: User = Depends(get_current_user)
):
    """Обновить чат-сессию"""
    session = await async_chat_manager.update_session(
        session_id, request.title, request.system_prompt
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": session}


@router.delete("/sessions/{session_id}")
async def admin_delete_chat_session(session_id: str, user: User = Depends(get_current_user)):
    """Удалить чат-сессию"""
    owner_id = None if user.role == "admin" else user.id
    if not await async_chat_manager.delete_session(session_id, owner_id=owner_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "ok"}


# ============== Messages Endpoints ==============


@router.post("/sessions/{session_id}/messages")
@limiter.limit(RATE_LIMIT_CHAT)
async def admin_send_chat_message(
    request: Request,
    session_id: str,
    msg_request: SendMessageRequest,
    user: User = Depends(get_current_user),
):
    """Отправить сообщение и получить ответ (non-streaming)"""
    container = get_container()
    owner_id = None if user.role == "admin" else user.id
    session = await async_chat_manager.get_session(session_id, owner_id=owner_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    llm_service = container.llm_service
    if not llm_service:
        raise HTTPException(status_code=503, detail="LLM service not available")

    # Добавляем сообщение пользователя
    user_msg = await async_chat_manager.add_message(session_id, "user", msg_request.content)

    # Получаем историю для LLM
    default_prompt = None
    if hasattr(llm_service, "get_system_prompt"):
        default_prompt = llm_service.get_system_prompt()
    messages = await async_chat_manager.get_messages_for_llm(session_id, default_prompt)

    # Генерируем ответ
    try:
        response_text = llm_service.generate_response_from_messages(messages, stream=False)
        if hasattr(response_text, "__iter__") and not isinstance(response_text, str):
            response_text = "".join(response_text)

        assistant_msg = await async_chat_manager.add_message(session_id, "assistant", response_text)
        return {"message": user_msg, "response": assistant_msg}

    except Exception as e:
        logger.error(f"❌ Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/stream")
@limiter.limit(RATE_LIMIT_CHAT)
async def admin_stream_chat_message(
    request: Request,
    session_id: str,
    msg_request: SendMessageRequest,
    user: User = Depends(get_current_user),
):
    """Отправить сообщение и получить streaming ответ"""
    container = get_container()
    owner_id = None if user.role == "admin" else user.id
    session = await async_chat_manager.get_session(session_id, owner_id=owner_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Per-instance rate limiting for telegram bot sessions
    if session.get("source") == "telegram_bot" and session.get("source_id"):
        bot_id = (
            session["source_id"].split(":")[0]
            if ":" in session["source_id"]
            else session["source_id"]
        )
        bot_config = await async_bot_instance_manager.get_instance(bot_id)
        if bot_config:
            rl_count = bot_config.get("rate_limit_count")
            rl_hours = bot_config.get("rate_limit_hours")
            if rl_count and rl_hours:
                since = datetime.utcnow() - timedelta(hours=rl_hours)
                msg_count = await async_chat_manager.count_messages(session_id, "user", since)
                if msg_count >= rl_count:
                    raise HTTPException(
                        status_code=429,
                        detail=f"Rate limit exceeded: {rl_count} messages per {rl_hours}h",
                    )

    # Determine which LLM service to use
    active_llm = container.llm_service
    custom_prompt = None

    if msg_request.llm_override:
        override = msg_request.llm_override
        backend = override.llm_backend

        if backend and backend.startswith("cloud:"):
            # Use specific cloud provider
            provider_id = backend.split(":", 1)[1]
            try:
                provider_config = await async_cloud_provider_manager.get_provider_with_key(
                    provider_id
                )
                if provider_config:
                    active_llm = CloudLLMService(provider_config)
                    logger.info(f"Using cloud provider: {provider_id}")
            except Exception as e:
                logger.warning(f"Failed to load cloud provider {provider_id}: {e}")
        elif backend == "gemini":
            # Legacy: auto-resolve to default Gemini cloud provider
            providers = await async_cloud_provider_manager.list_providers(enabled_only=True)
            gemini_p = next((p for p in providers if p.get("provider_type") == "gemini"), None)
            if gemini_p:
                try:
                    provider_config = await async_cloud_provider_manager.get_provider_with_key(
                        gemini_p["id"]
                    )
                    if provider_config:
                        active_llm = CloudLLMService(provider_config)
                        logger.info(f"Resolved gemini -> cloud:{gemini_p['id']}")
                except Exception as e:
                    logger.warning(f"Failed to load Gemini cloud provider: {e}")
        # else use default vllm/llm_service

        custom_prompt = override.system_prompt

    elif msg_request.widget_instance_id:
        widget = await async_widget_instance_manager.get_instance(msg_request.widget_instance_id)
        if widget:
            backend = widget.get("llm_backend")
            if backend and backend.startswith("cloud:"):
                provider_id = backend.split(":", 1)[1]
                try:
                    provider_config = await async_cloud_provider_manager.get_provider_with_key(
                        provider_id
                    )
                    if provider_config:
                        active_llm = CloudLLMService(provider_config)
                        logger.info(
                            f"Widget {msg_request.widget_instance_id}: using cloud provider {provider_id}"
                        )
                except Exception as e:
                    logger.warning(f"Widget LLM override failed: {e}")
            elif backend == "gemini":
                # Legacy: auto-resolve to default Gemini cloud provider
                providers = await async_cloud_provider_manager.list_providers(enabled_only=True)
                gemini_p = next((p for p in providers if p.get("provider_type") == "gemini"), None)
                if gemini_p:
                    try:
                        provider_config = await async_cloud_provider_manager.get_provider_with_key(
                            gemini_p["id"]
                        )
                        if provider_config:
                            active_llm = CloudLLMService(provider_config)
                            logger.info(
                                f"Widget {msg_request.widget_instance_id}: "
                                f"resolved gemini -> cloud:{gemini_p['id']}"
                            )
                    except Exception as e:
                        logger.warning(f"Widget Gemini cloud override failed: {e}")
            # else use default vllm/llm_service
            custom_prompt = widget.get("system_prompt")

    if not active_llm:
        raise HTTPException(status_code=503, detail="LLM service not available")

    # Добавляем сообщение пользователя
    user_msg = await async_chat_manager.add_message(session_id, "user", msg_request.content)

    # Получаем историю для LLM
    default_prompt = custom_prompt
    if not default_prompt and hasattr(active_llm, "get_system_prompt"):
        default_prompt = active_llm.get_system_prompt()

    # RAG: inject relevant wiki context into system prompt
    wiki_rag = container.wiki_rag_service
    if wiki_rag and default_prompt and msg_request.content:
        wiki_context = wiki_rag.retrieve(msg_request.content, top_k=3)
        if wiki_context:
            default_prompt = f"{default_prompt}\n\n{wiki_context}"

    messages = await async_chat_manager.get_messages_for_llm(session_id, default_prompt)

    async def generate_stream():
        full_response = []
        try:
            # Отправляем сообщение пользователя
            yield f"data: {json.dumps({'type': 'user_message', 'message': user_msg}, ensure_ascii=False)}\n\n"

            # Streaming ответ (use active_llm which may be overridden)
            for chunk in active_llm.generate_response_from_messages(messages, stream=True):
                full_response.append(chunk)
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"

            # Сохраняем полный ответ
            response_text = "".join(full_response)
            assistant_msg = await async_chat_manager.add_message(
                session_id, "assistant", response_text
            )

            # Отправляем финальное сообщение
            yield f"data: {json.dumps({'type': 'assistant_message', 'message': assistant_msg}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"❌ Chat stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.put("/sessions/{session_id}/messages/{message_id}")
async def admin_edit_chat_message(
    session_id: str,
    message_id: str,
    request: EditMessageRequest,
    user: User = Depends(get_current_user),
):
    """Редактировать сообщение пользователя и перегенерировать ответ"""
    container = get_container()
    owner_id = None if user.role == "admin" else user.id
    session = await async_chat_manager.get_session(session_id, owner_id=owner_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Находим сообщение
    message = None
    for msg in session["messages"]:
        if msg["id"] == message_id:
            message = msg
            break

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    if message["role"] != "user":
        raise HTTPException(status_code=400, detail="Can only edit user messages")

    # Удаляем это сообщение и все последующие
    await async_chat_manager.delete_message(session_id, message_id)

    # Добавляем отредактированное сообщение
    user_msg = await async_chat_manager.add_message(session_id, "user", request.content)

    llm_service = container.llm_service
    # Если был ответ после этого сообщения - генерируем новый
    if not llm_service:
        return {"message": user_msg}

    default_prompt = None
    if hasattr(llm_service, "get_system_prompt"):
        default_prompt = llm_service.get_system_prompt()
    messages = await async_chat_manager.get_messages_for_llm(session_id, default_prompt)

    try:
        response_text = llm_service.generate_response_from_messages(messages, stream=False)
        if hasattr(response_text, "__iter__") and not isinstance(response_text, str):
            response_text = "".join(response_text)

        assistant_msg = await async_chat_manager.add_message(session_id, "assistant", response_text)
        return {"message": user_msg, "response": assistant_msg}

    except Exception as e:
        logger.error(f"❌ Chat regenerate error: {e}")
        return {"message": user_msg, "error": str(e)}


@router.delete("/sessions/{session_id}/messages/{message_id}")
async def admin_delete_chat_message(
    session_id: str, message_id: str, user: User = Depends(get_current_user)
):
    """Удалить сообщение и все последующие"""
    if not await async_chat_manager.delete_message(session_id, message_id):
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "ok"}


@router.post("/sessions/{session_id}/messages/{message_id}/regenerate")
async def admin_regenerate_chat_response(
    session_id: str, message_id: str, user: User = Depends(get_current_user)
):
    """Перегенерировать ответ на сообщение"""
    container = get_container()
    owner_id = None if user.role == "admin" else user.id
    session = await async_chat_manager.get_session(session_id, owner_id=owner_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    llm_service = container.llm_service
    if not llm_service:
        raise HTTPException(status_code=503, detail="LLM service not available")

    # Находим сообщение пользователя
    message_index = -1
    for i, msg in enumerate(session["messages"]):
        if msg["id"] == message_id:
            message_index = i
            break

    if message_index == -1:
        raise HTTPException(status_code=404, detail="Message not found")

    # Если есть сообщение после этого - удаляем его (ответ ассистента)
    if message_index + 1 < len(session["messages"]):
        next_msg = session["messages"][message_index + 1]
        await async_chat_manager.delete_message(session_id, next_msg["id"])

    # Генерируем новый ответ
    default_prompt = None
    if hasattr(llm_service, "get_system_prompt"):
        default_prompt = llm_service.get_system_prompt()
    llm_messages = await async_chat_manager.get_messages_for_llm(session_id, default_prompt)

    try:
        response_text = llm_service.generate_response_from_messages(llm_messages, stream=False)
        if hasattr(response_text, "__iter__") and not isinstance(response_text, str):
            response_text = "".join(response_text)

        assistant_msg = await async_chat_manager.add_message(session_id, "assistant", response_text)
        return {"response": assistant_msg}

    except Exception as e:
        logger.error(f"❌ Chat regenerate error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
