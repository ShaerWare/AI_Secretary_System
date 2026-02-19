# app/routers/chat.py
"""Chat session router - sessions CRUD, messages, streaming."""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.dependencies import get_container
from app.rate_limiter import RATE_LIMIT_CHAT, limiter
from app.utils.tokens import count_message_tokens, get_context_window, trim_messages
from auth_manager import User, get_current_user
from cloud_llm_service import CloudLLMService
from db.integration import (
    async_bot_instance_manager,
    async_chat_manager,
    async_cloud_provider_manager,
    async_knowledge_collection_manager,
    async_whatsapp_instance_manager,
    async_widget_instance_manager,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/chat", tags=["chat"])

# Default system prompt for RAG-augmented conversations (when no custom prompt is set)
_DEFAULT_RAG_PROMPT = (
    "Ты — ИИ-секретарь. Отвечай на вопросы пользователя кратко и по делу, "
    "используя предоставленную документацию. Отвечай на языке пользователя."
)

# Anti-hallucination suffix — prevents Claude from generating fake tool calls as text
_NO_TOOLS_SUFFIX = (
    "\n\nВАЖНО: Ты — чат-бот без доступа к инструментам, файлам и командам. "
    "НИКОГДА не генерируй вызовы функций, tool_use, function_calls, "
    "filesystem, code execution или любые блоки вида `command { ... }`. "
    "Отвечай только обычным текстом. Используй markdown для форматирования."
)


def _inject_context_files(prompt: str | None, session: dict) -> str | None:
    """Inject context file contents into system prompt if session has any."""
    context_files = session.get("context_files")
    if not context_files:
        return prompt
    files_text = "\n\n".join(f"# {f['name']}\n{f['content']}" for f in context_files)
    base = prompt or _DEFAULT_RAG_PROMPT
    return f"{base}\n\n--- Прикреплённые файлы ---\n{files_text}"


def _finalize_prompt(prompt: str | None) -> str:
    """Add anti-tool-call suffix to any system prompt before sending to LLM."""
    base = prompt or _DEFAULT_RAG_PROMPT
    return base + _NO_TOOLS_SUFFIX


def _extract_collection_ids(data: dict) -> list[int]:
    """Extract collection IDs from config dict.

    Checks knowledge_collection_ids (JSON list) first,
    falls back to [knowledge_collection_id] for backward compat.
    """
    ids = data.get("knowledge_collection_ids")
    if ids and isinstance(ids, list):
        return [int(x) for x in ids if x is not None]
    # Backward compat: single collection_id
    single = data.get("knowledge_collection_id")
    if single is not None:
        return [int(single)]
    return []


async def _get_all_enabled_collection_ids() -> list[int]:
    """Get IDs of all enabled knowledge collections."""
    collections = await async_knowledge_collection_manager.get_all(enabled_only=True)
    return [c["id"] for c in collections]


async def _resolve_rag_config(
    session_data: dict,
    llm_override: Optional["LLMOverrideConfig"] = None,
    widget_instance_id: Optional[str] = None,
) -> tuple[str, list[int]]:
    """Resolve RAG mode and collection_ids from context.

    Returns (rag_mode, collection_ids):
    - "all" + [all enabled collection IDs]
    - "selected"/"collection" + [selected collection IDs]
    - "none" + []

    Priority chain: override → widget → telegram → whatsapp → session → default.
    """

    def _resolve_from_config(cfg: dict) -> tuple[str, list[int]] | None:
        mode = cfg.get("rag_mode")
        if not mode:
            return None
        ids = _extract_collection_ids(cfg)
        return mode, ids

    # 1. Explicit override from request
    if llm_override and llm_override.rag_mode:
        ids = []
        if llm_override.knowledge_collection_ids:
            ids = llm_override.knowledge_collection_ids
        elif llm_override.knowledge_collection_id is not None:
            ids = [llm_override.knowledge_collection_id]
        mode = llm_override.rag_mode
        if mode == "all":
            ids = await _get_all_enabled_collection_ids()
        return mode, ids

    # 2. Widget instance
    if widget_instance_id:
        widget = await async_widget_instance_manager.get_instance(widget_instance_id)
        if widget:
            result = _resolve_from_config(widget)
            if result:
                mode, ids = result
                if mode == "all":
                    ids = await _get_all_enabled_collection_ids()
                return mode, ids

    # 3. Telegram bot instance
    source = session_data.get("source")
    source_id = session_data.get("source_id")
    if source == "telegram_bot" and source_id:
        bot_id = source_id.split(":")[0] if ":" in source_id else source_id
        bot_config = await async_bot_instance_manager.get_instance(bot_id)
        if bot_config:
            result = _resolve_from_config(bot_config)
            if result:
                mode, ids = result
                if mode == "all":
                    ids = await _get_all_enabled_collection_ids()
                return mode, ids

    # 4. WhatsApp instance
    if source == "whatsapp" and source_id:
        wa_id = source_id.split(":")[0] if ":" in source_id else source_id
        wa_config = await async_whatsapp_instance_manager.get_instance(wa_id)
        if wa_config:
            result = _resolve_from_config(wa_config)
            if result:
                mode, ids = result
                if mode == "all":
                    ids = await _get_all_enabled_collection_ids()
                return mode, ids

    # 5. Session's own rag_mode
    result = _resolve_from_config(session_data)
    if result:
        mode, ids = result
        if mode == "all":
            ids = await _get_all_enabled_collection_ids()
        return mode, ids

    # 6. Default: all enabled collections
    return "all", await _get_all_enabled_collection_ids()


def _inject_rag_context(
    wiki_rag,
    user_content: str,
    base_prompt: Optional[str],
    rag_mode: str,
    collection_ids: list[int],
) -> Optional[str]:
    """Inject RAG context into system prompt based on rag_mode.

    Returns updated prompt or base_prompt unchanged if no RAG injection needed.
    collection_ids: list of collection IDs to search (resolved by _resolve_rag_config).
    """
    logger.info(
        f"RAG inject: mode={rag_mode}, ids={collection_ids}, "
        f"wiki_rag={'yes' if wiki_rag else 'NO'}, query={user_content[:80]!r}"
    )
    if not wiki_rag or not user_content or rag_mode == "none" or not collection_ids:
        logger.info(
            f"RAG inject: skipped (wiki_rag={bool(wiki_rag)}, "
            f"content={bool(user_content)}, mode={rag_mode}, ids={collection_ids})"
        )
        return base_prompt

    loaded_ids = (
        list(wiki_rag._collection_indexes.keys())
        if hasattr(wiki_rag, "_collection_indexes")
        else []
    )
    logger.info(f"RAG inject: loaded collection indexes: {loaded_ids}")

    if len(collection_ids) == 1:
        wiki_context = wiki_rag.retrieve(user_content, top_k=3, collection_id=collection_ids[0])
    else:
        wiki_context = wiki_rag.retrieve_multi(user_content, collection_ids, top_k=3)

    logger.info(
        f"RAG inject: context found={bool(wiki_context)}, len={len(wiki_context) if wiki_context else 0}"
    )

    if wiki_context:
        base = base_prompt or _DEFAULT_RAG_PROMPT
        rag_instruction = (
            "\n\n--- КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ (обязательно к использованию) ---\n"
            "Ниже приведена релевантная информация из базы знаний. "
            "ОБЯЗАТЕЛЬНО используй эти данные при ответе. "
            "Если информация ниже отвечает на вопрос пользователя — ответь на основе неё.\n"
        )
        return f"{base}{rag_instruction}\n{wiki_context}"

    return base_prompt


# ============== Token Counting Helpers ==============


def _get_model_name(llm_service) -> str:
    """Extract model name from LLM service for token counting."""
    if hasattr(llm_service, "model_name") and llm_service.model_name:
        return llm_service.model_name
    if hasattr(llm_service, "config") and isinstance(llm_service.config, dict):
        return llm_service.config.get("model_name", "")
    return "claude"


def _build_token_usage(messages: list[dict], model: str, trimmed: bool = False) -> dict:
    """Build token_usage dict for API responses."""
    tokens = count_message_tokens(messages, model)
    context_window = get_context_window(model)
    percent = round(tokens / context_window * 100, 1) if context_window else 0
    return {
        "tokens": tokens,
        "context_window": context_window,
        "percent": percent,
        "trimmed": trimmed,
    }


def _trim_and_log(messages: list[dict], model: str, session_id: str) -> tuple[list[dict], bool]:
    """Trim messages to fit context window and log if trimmed."""
    context_window = get_context_window(model)
    trimmed_messages, was_trimmed = trim_messages(messages, context_window)
    if was_trimmed:
        logger.info(
            f"Trimmed context for session {session_id}: "
            f"{len(messages)} -> {len(trimmed_messages)} messages"
        )
    return trimmed_messages, was_trimmed


# ============== Pydantic Models ==============


class CreateSessionRequest(BaseModel):
    title: Optional[str] = None
    system_prompt: Optional[str] = None
    source: Optional[str] = None  # "admin", "telegram", "widget"
    source_id: Optional[str] = None  # identifier (e.g., "bot_id:user_id")
    rag_mode: Optional[str] = None  # "all", "collection", "none"
    knowledge_collection_id: Optional[int] = None


class BulkDeleteRequest(BaseModel):
    session_ids: list[str]


class UpdateSessionRequest(BaseModel):
    title: Optional[str] = None
    system_prompt: Optional[str] = None
    pinned: Optional[bool] = None
    rag_mode: Optional[str] = None
    knowledge_collection_id: Optional[int] = None
    context_files: Optional[list] = None  # [{"name": str, "content": str}]


class LLMOverrideConfig(BaseModel):
    llm_backend: Optional[str] = None  # "vllm" or "cloud:provider-id"
    system_prompt: Optional[str] = None
    llm_params: Optional[dict] = None
    rag_mode: Optional[str] = None  # "all", "selected", "none" ("collection" = backward compat)
    knowledge_collection_id: Optional[int] = None  # backward compat (single)
    knowledge_collection_ids: Optional[list[int]] = None  # multi-select


class SendMessageRequest(BaseModel):
    content: str
    llm_override: Optional[LLMOverrideConfig] = None
    widget_instance_id: Optional[str] = None


class EditMessageRequest(BaseModel):
    content: str


class SwitchBranchRequest(BaseModel):
    message_id: str


# ============== Sessions Endpoints ==============


@router.get("/sessions")
async def admin_list_chat_sessions(
    group_by: Optional[str] = None,
    source: Optional[str] = Query(None),
    exclude_source: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
):
    """Список всех чат-сессий. group_by=source для группировки по источнику."""
    owner_id = None if user.role == "admin" else user.id
    if group_by == "source":
        grouped = await async_chat_manager.list_sessions_grouped(owner_id=owner_id)
        return {"sessions": grouped, "grouped": True}
    sessions = await async_chat_manager.list_sessions(
        owner_id=owner_id, source=source, exclude_source=exclude_source
    )
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
        rag_mode=request.rag_mode,
        knowledge_collection_id=request.knowledge_collection_id,
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

    # Include sibling info for branch navigation
    sibling_info = await async_chat_manager.get_sibling_info(session_id)
    session["sibling_info"] = sibling_info

    # Token usage info
    llm_service = get_container().llm_service
    model = _get_model_name(llm_service) if llm_service else "claude"
    llm_messages = [
        {"role": m["role"], "content": m["content"]} for m in session.get("messages", [])
    ]
    session["token_usage"] = _build_token_usage(llm_messages, model)

    return {"session": session}


@router.put("/sessions/{session_id}")
async def admin_update_chat_session(
    session_id: str, request: UpdateSessionRequest, user: User = Depends(get_current_user)
):
    """Обновить чат-сессию"""
    session = await async_chat_manager.update_session(
        session_id,
        request.title,
        request.system_prompt,
        pinned=request.pinned,
        rag_mode=request.rag_mode,
        knowledge_collection_id=request.knowledge_collection_id,
        context_files=request.context_files,
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
    # Session prompt takes priority; fallback to LLM service default
    default_prompt = session.get("system_prompt")
    if not default_prompt and hasattr(llm_service, "get_system_prompt"):
        default_prompt = llm_service.get_system_prompt()

    # RAG: inject relevant wiki context based on rag_mode
    rag_mode, collection_ids = await _resolve_rag_config(session, msg_request.llm_override)
    default_prompt = _inject_rag_context(
        container.wiki_rag_service, msg_request.content, default_prompt, rag_mode, collection_ids
    )

    # Inject context files
    default_prompt = _inject_context_files(default_prompt, session)

    messages = await async_chat_manager.get_messages_for_llm(
        session_id, _finalize_prompt(default_prompt)
    )

    # Trim to fit context window
    model = _get_model_name(llm_service)
    messages, _ = _trim_and_log(messages, model, session_id)

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
    # Priority: widget prompt > session prompt > LLM service default
    default_prompt = custom_prompt or session.get("system_prompt")
    if not default_prompt and hasattr(active_llm, "get_system_prompt"):
        default_prompt = active_llm.get_system_prompt()

    # RAG: inject relevant wiki context based on rag_mode
    rag_mode, collection_ids = await _resolve_rag_config(
        session, msg_request.llm_override, msg_request.widget_instance_id
    )
    default_prompt = _inject_rag_context(
        container.wiki_rag_service, msg_request.content, default_prompt, rag_mode, collection_ids
    )

    # Inject context files
    default_prompt = _inject_context_files(default_prompt, session)

    messages = await async_chat_manager.get_messages_for_llm(
        session_id, _finalize_prompt(default_prompt)
    )

    # Trim to fit context window
    model = _get_model_name(active_llm)
    messages, was_trimmed = _trim_and_log(messages, model, session_id)

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

            # Build token_usage for the final event
            all_msgs = messages + [{"role": "assistant", "content": response_text}]
            token_usage = _build_token_usage(all_msgs, model, was_trimmed)

            # Отправляем финальное сообщение
            yield f"data: {json.dumps({'type': 'assistant_message', 'message': assistant_msg, 'token_usage': token_usage}, ensure_ascii=False)}\n\n"
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
    """Редактировать сообщение (non-destructive: creates new branch)"""
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

    if message["role"] not in ("user", "assistant"):
        raise HTTPException(status_code=400, detail="Cannot edit system messages")

    # Non-destructive edit: creates sibling branch, deactivates old
    edited_msg = await async_chat_manager.edit_message(session_id, message_id, request.content)

    # Assistant edits: just save the new text, no LLM regeneration
    if message["role"] == "assistant":
        return {"message": edited_msg}

    # User edits: generate new LLM response for the edited message
    llm_service = container.llm_service
    if not llm_service:
        return {"message": edited_msg}

    default_prompt = session.get("system_prompt")
    if not default_prompt and hasattr(llm_service, "get_system_prompt"):
        default_prompt = llm_service.get_system_prompt()

    # RAG: inject relevant wiki context based on rag_mode
    rag_mode, collection_ids = await _resolve_rag_config(session)
    default_prompt = _inject_rag_context(
        container.wiki_rag_service, request.content, default_prompt, rag_mode, collection_ids
    )

    # Inject context files
    default_prompt = _inject_context_files(default_prompt, session)

    messages = await async_chat_manager.get_messages_for_llm(
        session_id, _finalize_prompt(default_prompt)
    )

    # Trim to fit context window
    model = _get_model_name(llm_service)
    messages, _ = _trim_and_log(messages, model, session_id)

    try:
        response_text = llm_service.generate_response_from_messages(messages, stream=False)
        if hasattr(response_text, "__iter__") and not isinstance(response_text, str):
            response_text = "".join(response_text)

        # Add response as child of the new edited message
        assistant_msg = await async_chat_manager.add_message(
            session_id, "assistant", response_text, parent_id=edited_msg["id"]
        )
        return {"message": edited_msg, "response": assistant_msg}

    except Exception as e:
        logger.error(f"❌ Chat regenerate error: {e}")
        return {"message": edited_msg, "error": str(e)}


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
    """Перегенерировать ответ (non-destructive: creates new branch)"""
    container = get_container()
    owner_id = None if user.role == "admin" else user.id
    session = await async_chat_manager.get_session(session_id, owner_id=owner_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    llm_service = container.llm_service
    if not llm_service:
        raise HTTPException(status_code=503, detail="LLM service not available")

    # Find the message to regenerate
    target_msg = None
    for msg in session["messages"]:
        if msg["id"] == message_id:
            target_msg = msg
            break

    if not target_msg:
        raise HTTPException(status_code=404, detail="Message not found")

    # Determine the user message that should be the parent of the new response
    if target_msg["role"] == "assistant":
        # Regenerate assistant message: deactivate it, add new sibling
        parent_msg = await async_chat_manager.branch_regenerate(session_id, message_id)
        if not parent_msg:
            raise HTTPException(status_code=500, detail="Failed to prepare regeneration")
        parent_id = parent_msg["id"]
    else:
        # Regenerating from a user message: find and deactivate existing assistant response
        # Look for active assistant children
        for i, msg in enumerate(session["messages"]):
            if msg["id"] == message_id:
                # Check if next message is assistant
                if i + 1 < len(session["messages"]):
                    next_msg = session["messages"][i + 1]
                    if next_msg["role"] == "assistant":
                        await async_chat_manager.branch_regenerate(session_id, next_msg["id"])
                break
        parent_id = message_id

    # Generate new response
    default_prompt = session.get("system_prompt")
    if not default_prompt and hasattr(llm_service, "get_system_prompt"):
        default_prompt = llm_service.get_system_prompt()

    # RAG: inject relevant wiki context based on rag_mode
    user_content = target_msg["content"] if target_msg["role"] == "user" else ""
    rag_mode, collection_ids = await _resolve_rag_config(session)
    default_prompt = _inject_rag_context(
        container.wiki_rag_service, user_content, default_prompt, rag_mode, collection_ids
    )

    # Inject context files
    default_prompt = _inject_context_files(default_prompt, session)

    llm_messages = await async_chat_manager.get_messages_for_llm(
        session_id, _finalize_prompt(default_prompt)
    )

    # Trim to fit context window
    model = _get_model_name(llm_service)
    llm_messages, _ = _trim_and_log(llm_messages, model, session_id)

    try:
        response_text = llm_service.generate_response_from_messages(llm_messages, stream=False)
        if hasattr(response_text, "__iter__") and not isinstance(response_text, str):
            response_text = "".join(response_text)

        assistant_msg = await async_chat_manager.add_message(
            session_id, "assistant", response_text, parent_id=parent_id
        )
        return {"response": assistant_msg}

    except Exception as e:
        logger.error(f"❌ Chat regenerate error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Summarize Endpoint ==============


@router.post("/sessions/{session_id}/messages/{message_id}/summarize")
async def admin_summarize_branch(
    session_id: str, message_id: str, user: User = Depends(get_current_user)
):
    """Сгенерировать итоги ветки диалога и вернуть как markdown."""
    container = get_container()
    owner_id = None if user.role == "admin" else user.id
    session = await async_chat_manager.get_session(session_id, owner_id=owner_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    llm_service = container.llm_service
    if not llm_service:
        raise HTTPException(status_code=503, detail="LLM service not available")

    # Get branch path from root to this message
    branch_messages = await async_chat_manager.get_branch_path(session_id, message_id)
    if not branch_messages:
        raise HTTPException(status_code=404, detail="Message not found")

    # Build LLM request with summarize instruction
    summarize_prompt = (
        "Проанализируй следующий диалог и создай структурированный markdown-документ с итогами. "
        "Включи: основные темы, ключевые решения, выводы и открытые вопросы. "
        "Пиши на языке диалога. Отвечай ТОЛЬКО markdown-документом без пояснений."
    )
    dialog_text = "\n\n".join(f"**{m['role']}**: {m['content']}" for m in branch_messages)
    messages = [
        {"role": "system", "content": _finalize_prompt(summarize_prompt)},
        {"role": "user", "content": dialog_text},
    ]

    try:
        response_text = llm_service.generate_response_from_messages(messages, stream=False)
        if hasattr(response_text, "__iter__") and not isinstance(response_text, str):
            response_text = "".join(response_text)
        return {"summary": response_text}
    except Exception as e:
        logger.error(f"❌ Summarize error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Branch Endpoints ==============


@router.get("/sessions/{session_id}/branches")
async def admin_get_branch_tree(session_id: str, user: User = Depends(get_current_user)):
    """Получить дерево веток чата"""
    branches = await async_chat_manager.get_branch_tree(session_id)
    return {"branches": branches}


@router.post("/sessions/{session_id}/branches/switch")
async def admin_switch_branch(
    session_id: str,
    request: SwitchBranchRequest,
    user: User = Depends(get_current_user),
):
    """Переключить активную ветку"""
    success = await async_chat_manager.switch_branch(session_id, request.message_id)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")

    # Return updated session
    session = await async_chat_manager.get_session(session_id)
    if session:
        sibling_info = await async_chat_manager.get_sibling_info(session_id)
        session["sibling_info"] = sibling_info
    return {"status": "ok", "session": session}


@router.post("/sessions/{session_id}/branches/new")
async def admin_new_branch(
    session_id: str,
    user: User = Depends(get_current_user),
):
    """Начать новую ветку с чистого листа (деактивирует все сообщения)"""
    success = await async_chat_manager.start_new_branch(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    session = await async_chat_manager.get_session(session_id)
    sibling_info = await async_chat_manager.get_sibling_info(session_id)
    if session:
        session["sibling_info"] = sibling_info
    return {"status": "ok", "session": session}
