# app/routers/chat.py
"""Chat session router - sessions CRUD, messages, streaming."""

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.dependencies import get_container
from cloud_llm_service import CloudLLMService
from db.integration import async_chat_manager, async_cloud_provider_manager
from llm_service import LLMService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/chat", tags=["chat"])


# ============== Pydantic Models ==============


class CreateSessionRequest(BaseModel):
    title: Optional[str] = None
    system_prompt: Optional[str] = None


class UpdateSessionRequest(BaseModel):
    title: Optional[str] = None
    system_prompt: Optional[str] = None


class LLMOverrideConfig(BaseModel):
    llm_backend: Optional[str] = None  # "vllm", "gemini", or "cloud:provider-id"
    system_prompt: Optional[str] = None
    llm_params: Optional[dict] = None


class SendMessageRequest(BaseModel):
    content: str
    llm_override: Optional[LLMOverrideConfig] = None


class EditMessageRequest(BaseModel):
    content: str


# ============== Sessions Endpoints ==============


@router.get("/sessions")
async def admin_list_chat_sessions():
    """Список всех чат-сессий"""
    sessions = await async_chat_manager.list_sessions()
    return {"sessions": sessions}


@router.post("/sessions")
async def admin_create_chat_session(request: CreateSessionRequest):
    """Создать новую чат-сессию"""
    session = await async_chat_manager.create_session(request.title, request.system_prompt)
    return {"session": session}


@router.get("/sessions/{session_id}")
async def admin_get_chat_session(session_id: str):
    """Получить чат-сессию"""
    session = await async_chat_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": session}


@router.put("/sessions/{session_id}")
async def admin_update_chat_session(session_id: str, request: UpdateSessionRequest):
    """Обновить чат-сессию"""
    session = await async_chat_manager.update_session(
        session_id, request.title, request.system_prompt
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": session}


@router.delete("/sessions/{session_id}")
async def admin_delete_chat_session(session_id: str):
    """Удалить чат-сессию"""
    if not await async_chat_manager.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "ok"}


# ============== Messages Endpoints ==============


@router.post("/sessions/{session_id}/messages")
async def admin_send_chat_message(session_id: str, request: SendMessageRequest):
    """Отправить сообщение и получить ответ (non-streaming)"""
    container = get_container()
    session = await async_chat_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    llm_service = container.llm_service
    if not llm_service:
        raise HTTPException(status_code=503, detail="LLM service not available")

    # Добавляем сообщение пользователя
    user_msg = await async_chat_manager.add_message(session_id, "user", request.content)

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
async def admin_stream_chat_message(session_id: str, request: SendMessageRequest):
    """Отправить сообщение и получить streaming ответ"""
    container = get_container()
    session = await async_chat_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Determine which LLM service to use
    active_llm = container.llm_service
    custom_prompt = None

    if request.llm_override:
        override = request.llm_override
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
            # Use Gemini (LLMService from llm_service.py)
            try:
                active_llm = LLMService()
                logger.info("Using Gemini LLM for override")
            except Exception as e:
                logger.warning(f"Failed to create Gemini LLM: {e}")
        # else use default vllm/llm_service

        custom_prompt = override.system_prompt

    if not active_llm:
        raise HTTPException(status_code=503, detail="LLM service not available")

    # Добавляем сообщение пользователя
    user_msg = await async_chat_manager.add_message(session_id, "user", request.content)

    # Получаем историю для LLM
    default_prompt = custom_prompt
    if not default_prompt and hasattr(active_llm, "get_system_prompt"):
        default_prompt = active_llm.get_system_prompt()
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
async def admin_edit_chat_message(session_id: str, message_id: str, request: EditMessageRequest):
    """Редактировать сообщение пользователя и перегенерировать ответ"""
    container = get_container()
    session = await async_chat_manager.get_session(session_id)
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
async def admin_delete_chat_message(session_id: str, message_id: str):
    """Удалить сообщение и все последующие"""
    if not await async_chat_manager.delete_message(session_id, message_id):
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "ok"}


@router.post("/sessions/{session_id}/messages/{message_id}/regenerate")
async def admin_regenerate_chat_response(session_id: str, message_id: str):
    """Перегенерировать ответ на сообщение"""
    container = get_container()
    session = await async_chat_manager.get_session(session_id)
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
