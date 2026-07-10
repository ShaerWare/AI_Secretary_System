# modules/chat/router.py
"""Chat session router - sessions CRUD, messages, streaming."""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.dependencies import get_container
from app.rate_limiter import RATE_LIMIT_CHAT, limiter
from app.utils.tokens import count_message_tokens, get_context_window
from auth_manager import (
    User,
    get_optional_user,
    get_user_permissions,
    level_gte,
    require_permission,
    resolve_user_from_token,
    user_has_level,
    workspace_context,
)
from cloud_llm_service import CloudLLMService
from modules.channels.mobile.service import mobile_app_instance_service
from modules.channels.telegram.service import bot_instance_service
from modules.channels.whatsapp.service import whatsapp_instance_service
from modules.channels.widget.service import widget_instance_service
from modules.chat.facade import ChatServiceImpl, chat_service_facade
from modules.chat.service import chat_service, chat_share_service
from modules.knowledge.service import knowledge_collection_service
from modules.llm.service import cloud_provider_service


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

# Temporary cache for OCR text from uploaded images (upload → send are two separate requests)
_pending_image_ocr: dict[str, str] = {}

_AGENTIC_RAG_SUFFIX = (
    "\n\nУ тебя есть инструмент knowledge_search для поиска по базе знаний. "
    "Используй его когда вопрос связан с документацией или требует фактических данных. "
    "Можешь вызвать несколько раз с разными запросами. "
    "Не выдумывай — если не нашёл информацию, честно скажи."
)

_WEB_SEARCH_SUFFIX = (
    "\n\nУ тебя есть инструмент web_search для поиска в интернете. "
    "Используй его когда нужна актуальная информация: новости, цены, погода, "
    "события, факты. Можешь вызвать несколько раз с разными запросами."
)


def _finalize_prompt(
    prompt: str | None, agentic_rag: bool = False, web_search: bool = False
) -> str:
    """Add suffix to system prompt: agentic RAG / web search instructions or anti-tool-call guard."""
    base = prompt or _DEFAULT_RAG_PROMPT
    if not agentic_rag and not web_search:
        return base + _NO_TOOLS_SUFFIX
    result = base
    if agentic_rag:
        result += _AGENTIC_RAG_SUFFIX
    if web_search:
        result += _WEB_SEARCH_SUFFIX
    return result


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
    collections = await knowledge_collection_service.get_all(enabled_only=True)
    return [c["id"] for c in collections]


async def _resolve_rag_config(
    session_data: dict,
    llm_override: Optional["LLMOverrideConfig"] = None,
    widget_instance_id: Optional[str] = None,
    mobile_instance_id: Optional[str] = None,
) -> tuple[str, list[int]]:
    """Resolve RAG mode and collection_ids from context.

    Returns (rag_mode, collection_ids):
    - "all" + [all enabled collection IDs]
    - "selected"/"collection" + [selected collection IDs]
    - "none" + []

    Priority chain: override → widget → mobile → telegram → whatsapp → session → default.
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
        widget = await widget_instance_service.get_instance(widget_instance_id)
        if widget:
            result = _resolve_from_config(widget)
            if result:
                mode, ids = result
                if mode == "all":
                    ids = await _get_all_enabled_collection_ids()
                return mode, ids

    # 3. Mobile app instance
    if mobile_instance_id:
        mobile_inst = await mobile_app_instance_service.get_instance(mobile_instance_id)
        if mobile_inst:
            result = _resolve_from_config(mobile_inst)
            if result:
                mode, ids = result
                if mode == "all":
                    ids = await _get_all_enabled_collection_ids()
                return mode, ids

    # 4. Telegram bot instance
    source = session_data.get("source")
    source_id = session_data.get("source_id")
    if source == "telegram_bot" and source_id:
        bot_id = source_id.split(":")[0] if ":" in source_id else source_id
        bot_config = await bot_instance_service.get_instance(bot_id)
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
        wa_config = await whatsapp_instance_service.get_instance(wa_id)
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
    knowledge_collection_ids: Optional[list[int]] = None
    context_files: Optional[list] = None  # [{"name": str, "content": str}]
    web_search_enabled: Optional[bool] = None
    source: Optional[str] = None  # "admin", "mobile", "telegram", "widget"
    source_id: Optional[str] = None  # e.g. mobile_app_instance id


class LLMOverrideConfig(BaseModel):
    llm_backend: Optional[str] = None  # "vllm" or "cloud:provider-id"
    system_prompt: Optional[str] = None
    llm_params: Optional[dict] = None
    rag_mode: Optional[str] = None  # "all", "selected", "none" ("collection" = backward compat)
    knowledge_collection_id: Optional[int] = None  # backward compat (single)
    knowledge_collection_ids: Optional[list[int]] = None  # multi-select


class SendMessageRequest(BaseModel):
    content: str
    image_ids: Optional[list[str]] = None
    llm_override: Optional[LLMOverrideConfig] = None
    widget_instance_id: Optional[str] = None
    mobile_instance_id: Optional[str] = None


class EditMessageRequest(BaseModel):
    content: str


class SwitchBranchRequest(BaseModel):
    message_id: str


class RenameBranchRequest(BaseModel):
    branch_name: str


class ShareSessionRequest(BaseModel):
    user_id: int
    permission: str = "read"  # "read" or "write"


class UpdateShareRequest(BaseModel):
    permission: str  # "read" or "write"


class ForkSessionRequest(BaseModel):
    title: Optional[str] = None


# ============== Share Helpers ==============


async def _check_session_owner_or_admin(session_id: str, user: User) -> dict:
    """Verify user is session owner or admin. Returns session data."""
    session_data = await chat_service.get_session(session_id, workspace_id=user.workspace_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")
    if not user_has_level(user, "chat", "manage") and session_data.get("owner_id") not in (
        user.id,
        None,
    ):
        raise HTTPException(status_code=403, detail="Only session owner or admin can manage shares")
    return session_data


async def _check_write_access(session_id: str, user: User) -> dict:
    """Check that user has write access to session. Returns session data."""
    ws_id = user.workspace_id
    # Manager always has access
    if user_has_level(user, "chat", "manage"):
        session_data = await chat_service.get_session(session_id, workspace_id=ws_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")
        return session_data

    # Owner has access
    session_data = await chat_service.get_session(session_id, owner_id=user.id, workspace_id=ws_id)
    if session_data:
        owner_id = session_data.get("owner_id")
        if owner_id == user.id or owner_id is None:
            return session_data
        # Session found via share — check write permission
        perm = await chat_share_service.get_user_permission(session_id, user.id)
        if perm == "write":
            return session_data
        raise HTTPException(status_code=403, detail="Read-only access")

    raise HTTPException(status_code=404, detail="Session not found")


# ============== Sessions Endpoints ==============


@router.get("/sessions")
async def admin_list_chat_sessions(
    group_by: Optional[str] = None,
    source: Optional[str] = Query(None),
    exclude_source: Optional[str] = Query(None),
    user: User = Depends(require_permission("chat", "view")),
):
    """Список всех чат-сессий. group_by=source для группировки по источнику."""
    owner_id, ws_id = workspace_context(user, "chat")

    # Get shared session permissions for non-admin users
    shared_perms: dict[str, str] = {}
    if owner_id is not None:
        shared_perms = await chat_share_service.get_shared_sessions_with_permissions(user.id)

    # Check default mobile session for current user
    default_mobile_sid = await chat_share_service.get_user_default_mobile_session(user.id)

    def _enrich(sessions_list: list[dict], share_counts: dict[str, int]) -> list[dict]:
        for s in sessions_list:
            sid = s.get("id", "")
            s_owner = s.get("owner_id")
            if sid in shared_perms and s_owner != user.id:
                s["is_shared_with_me"] = True
                s["share_permission"] = shared_perms[sid]
            else:
                s["is_shared_with_me"] = False
                s["share_permission"] = "owner"
            s["share_count"] = share_counts.get(sid, 0)
            s["is_default_mobile"] = sid == default_mobile_sid
        return sessions_list

    if group_by == "source":
        grouped = await chat_service.list_sessions_grouped(owner_id=owner_id, workspace_id=ws_id)
        all_ids = [s["id"] for sl in grouped.values() for s in sl]
        share_counts = await chat_share_service.get_share_counts(all_ids) if all_ids else {}
        for source_key in grouped:
            _enrich(grouped[source_key], share_counts)
        return {"sessions": grouped, "grouped": True}
    sessions = await chat_service.list_sessions(
        owner_id=owner_id, source=source, exclude_source=exclude_source, workspace_id=ws_id
    )
    all_ids = [s["id"] for s in sessions]
    share_counts = await chat_share_service.get_share_counts(all_ids) if all_ids else {}
    _enrich(sessions, share_counts)
    return {"sessions": sessions}


@router.post("/sessions")
async def admin_create_chat_session(
    request: CreateSessionRequest, user: User = Depends(require_permission("chat", "edit"))
):
    """Создать новую чат-сессию"""
    owner_id, ws_id = workspace_context(user, "chat")

    # Auto-apply instance system_prompt + RAG config when not explicitly
    # provided. Lets the frontend create a session with just `source` +
    # `source_id` (e.g. assistant switcher) and inherit the persona.
    system_prompt = request.system_prompt
    rag_mode = request.rag_mode
    inherited_collection_ids: list[int] | None = None
    if request.source == "widget" and request.source_id:
        widget = await widget_instance_service.get_instance(request.source_id)
        if widget:
            if not system_prompt and widget.get("system_prompt"):
                system_prompt = widget["system_prompt"]
            if not rag_mode and widget.get("rag_mode"):
                rag_mode = widget["rag_mode"]
            if not request.knowledge_collection_id and widget.get("knowledge_collection_ids"):
                inherited_collection_ids = widget["knowledge_collection_ids"]
    elif request.source == "mobile" and request.source_id:
        mobile_inst = await mobile_app_instance_service.get_instance(request.source_id)
        if mobile_inst:
            if not system_prompt and mobile_inst.get("system_prompt"):
                system_prompt = mobile_inst["system_prompt"]
            if not rag_mode and mobile_inst.get("rag_mode"):
                rag_mode = mobile_inst["rag_mode"]
            if not request.knowledge_collection_id and mobile_inst.get("knowledge_collection_ids"):
                inherited_collection_ids = mobile_inst["knowledge_collection_ids"]

    session = await chat_service.create_session(
        request.title,
        system_prompt,
        request.source,
        request.source_id,
        owner_id=owner_id,
        rag_mode=rag_mode,
        knowledge_collection_id=request.knowledge_collection_id,
        workspace_id=ws_id,
    )

    # Persist inherited multi-collection RAG selection in a follow-up update
    # (create_session takes a single legacy id; update_session takes the list).
    if inherited_collection_ids:
        updated = await chat_service.update_session(
            session["id"],
            knowledge_collection_ids=inherited_collection_ids,
        )
        if updated:
            session = updated

    return {"session": session}


@router.post("/sessions/bulk-delete")
async def admin_bulk_delete_sessions(
    request: BulkDeleteRequest, user: User = Depends(require_permission("chat", "manage"))
):
    """Удалить несколько сессий сразу"""
    owner_id, ws_id = workspace_context(user, "chat")
    count = await chat_service.delete_sessions_bulk(
        request.session_ids, owner_id=owner_id, workspace_id=ws_id
    )
    return {"status": "ok", "deleted": count}


@router.get("/sessions/{session_id}")
async def admin_get_chat_session(
    session_id: str, user: User = Depends(require_permission("chat", "view"))
):
    """Получить чат-сессию"""
    owner_id, ws_id = workspace_context(user, "chat")
    session = await chat_service.get_session(session_id, owner_id=owner_id, workspace_id=ws_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Include sibling info for branch navigation
    sibling_info = await chat_service.get_sibling_info(session_id)
    session["sibling_info"] = sibling_info

    # Token usage info
    llm_service = get_container().llm_service
    model = _get_model_name(llm_service) if llm_service else "claude"
    llm_messages = [
        {"role": m["role"], "content": m["content"]} for m in session.get("messages", [])
    ]
    session["token_usage"] = _build_token_usage(llm_messages, model)

    # Share info
    session_owner_id = session.get("owner_id")
    is_owner = user_has_level(user, "chat", "manage") or session_owner_id == user.id
    if is_owner:
        session["is_shared_with_me"] = False
        session["share_permission"] = "owner"
        shares = await chat_share_service.get_shares(session_id)
        session["share_count"] = len(shares)
    else:
        perm = await chat_share_service.get_user_permission(session_id, user.id)
        session["is_shared_with_me"] = True
        session["share_permission"] = perm or "read"
        session["share_count"] = 0

    return {"session": session}


@router.put("/sessions/{session_id}")
async def admin_update_chat_session(
    session_id: str,
    request: UpdateSessionRequest,
    user: User = Depends(require_permission("chat", "edit")),
):
    """Обновить чат-сессию"""
    await _check_write_access(session_id, user)
    session = await chat_service.update_session(
        session_id,
        request.title,
        request.system_prompt,
        pinned=request.pinned,
        rag_mode=request.rag_mode,
        knowledge_collection_id=request.knowledge_collection_id,
        knowledge_collection_ids=request.knowledge_collection_ids,
        context_files=request.context_files,
        web_search_enabled=request.web_search_enabled,
        source=request.source,
        source_id=request.source_id,
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": session}


@router.delete("/sessions/{session_id}")
async def admin_delete_chat_session(
    session_id: str, user: User = Depends(require_permission("chat", "edit"))
):
    """Удалить чат-сессию (owner/admin only, shared users cannot delete)"""
    await _check_session_owner_or_admin(session_id, user)
    owner_id, ws_id = workspace_context(user, "chat")
    if not await chat_service.delete_session(session_id, owner_id=owner_id, workspace_id=ws_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "ok"}


# ============== Messages Endpoints ==============


@router.post("/sessions/{session_id}/messages")
@limiter.limit(RATE_LIMIT_CHAT)
async def admin_send_chat_message(
    request: Request,
    session_id: str,
    msg_request: SendMessageRequest,
    user: User = Depends(require_permission("chat", "edit")),
):
    """Отправить сообщение и получить ответ (non-streaming)"""
    container = get_container()
    session = await _check_write_access(session_id, user)

    llm_service = container.llm_service
    if not llm_service:
        raise HTTPException(status_code=503, detail="LLM service not available")

    # Добавляем сообщение пользователя (with image metadata if any)
    extra_data_json_ns = None
    image_ocr_parts_ns: list[str] = []
    if msg_request.image_ids:
        from modules.chat.image_service import IMAGES_DIR

        images_meta_ns = []
        for img_id in msg_request.image_ids:
            session_dir = IMAGES_DIR / session_id
            if not session_dir.exists():
                continue
            for f in session_dir.iterdir():
                if f.name.startswith(img_id) and not f.name.endswith("_thumb.jpg"):
                    images_meta_ns.append(
                        {
                            "id": img_id,
                            "filename": f.name,
                            "url": f"/admin/chat/images/{session_id}/{f.name}",
                            "thumb_url": f"/admin/chat/images/{session_id}/{img_id}_thumb.jpg",
                        }
                    )
                    break
            ocr = _pending_image_ocr.pop(img_id, None)
            if ocr:
                image_ocr_parts_ns.append(ocr)
        if images_meta_ns:
            extra_data_json_ns = json.dumps({"images": images_meta_ns}, ensure_ascii=False)

    llm_content_ns = msg_request.content
    if image_ocr_parts_ns:
        ocr_block = "\n\n".join(f"[Текст с изображения]:\n{ocr}" for ocr in image_ocr_parts_ns)
        llm_content_ns = (
            f"{msg_request.content}\n\n{ocr_block}" if msg_request.content else ocr_block
        )

    user_msg = await chat_service.add_message(
        session_id, "user", llm_content_ns, extra_data=extra_data_json_ns
    )

    # Resolve RAG config
    rag_mode, collection_ids = await _resolve_rag_config(session, msg_request.llm_override)

    # Delegate generation to ChatService facade
    facade = chat_service_facade or ChatServiceImpl(container)
    try:
        assistant_msg = await facade.send_message(
            session_id,
            llm_content_ns,
            llm_service=llm_service,
            session_data=session,
            rag_mode=rag_mode,
            collection_ids=collection_ids,
        )
        return {"message": user_msg, "response": assistant_msg}
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/stream")
@limiter.limit(RATE_LIMIT_CHAT)
async def admin_stream_chat_message(
    request: Request,
    session_id: str,
    msg_request: SendMessageRequest,
    user: User = Depends(require_permission("chat", "edit")),
):
    """Отправить сообщение и получить streaming ответ"""
    container = get_container()
    session = await _check_write_access(session_id, user)

    # Per-instance rate limiting for telegram bot sessions
    if session.get("source") == "telegram_bot" and session.get("source_id"):
        bot_id = (
            session["source_id"].split(":")[0]
            if ":" in session["source_id"]
            else session["source_id"]
        )
        bot_config = await bot_instance_service.get_instance(bot_id)
        if bot_config:
            rl_count = bot_config.get("rate_limit_count")
            rl_hours = bot_config.get("rate_limit_hours")
            if rl_count and rl_hours:
                since = datetime.utcnow() - timedelta(hours=rl_hours)
                msg_count = await chat_service.count_messages(session_id, "user", since)
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
                provider_config = await cloud_provider_service.get_provider_with_key(provider_id)
                if provider_config:
                    active_llm = CloudLLMService(provider_config)
                    logger.info(f"Using cloud provider: {provider_id}")
            except Exception as e:
                logger.warning(f"Failed to load cloud provider {provider_id}: {e}")
        elif backend == "gemini":
            # Legacy: auto-resolve to default Gemini cloud provider
            providers = await cloud_provider_service.list_providers(enabled_only=True)
            gemini_p = next((p for p in providers if p.get("provider_type") == "gemini"), None)
            if gemini_p:
                try:
                    provider_config = await cloud_provider_service.get_provider_with_key(
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
        widget = await widget_instance_service.get_instance(msg_request.widget_instance_id)
        if widget:
            backend = widget.get("llm_backend")
            if backend and backend.startswith("cloud:"):
                provider_id = backend.split(":", 1)[1]
                try:
                    provider_config = await cloud_provider_service.get_provider_with_key(
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
                providers = await cloud_provider_service.list_providers(enabled_only=True)
                gemini_p = next((p for p in providers if p.get("provider_type") == "gemini"), None)
                if gemini_p:
                    try:
                        provider_config = await cloud_provider_service.get_provider_with_key(
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

    elif msg_request.mobile_instance_id:
        mobile_inst = await mobile_app_instance_service.get_instance(msg_request.mobile_instance_id)
        if mobile_inst:
            backend = mobile_inst.get("llm_backend")
            if backend and backend.startswith("cloud:"):
                provider_id = backend.split(":", 1)[1]
                try:
                    provider_config = await cloud_provider_service.get_provider_with_key(
                        provider_id
                    )
                    if provider_config:
                        active_llm = CloudLLMService(provider_config)
                        logger.info(
                            f"Mobile {msg_request.mobile_instance_id}: "
                            f"using cloud provider {provider_id}"
                        )
                except Exception as e:
                    logger.warning(f"Mobile LLM override failed: {e}")
            custom_prompt = mobile_inst.get("system_prompt")

    if not active_llm:
        raise HTTPException(status_code=503, detail="LLM service not available")

    # Добавляем сообщение пользователя (with image metadata if any)
    extra_data_json = None
    image_ocr_parts: list[str] = []

    if msg_request.image_ids:
        from modules.chat.image_service import IMAGES_DIR

        images_meta = []
        for img_id in msg_request.image_ids:
            session_dir = IMAGES_DIR / session_id
            if not session_dir.exists():
                continue
            for f in session_dir.iterdir():
                if f.name.startswith(img_id) and not f.name.endswith("_thumb.jpg"):
                    images_meta.append(
                        {
                            "id": img_id,
                            "filename": f.name,
                            "url": f"/admin/chat/images/{session_id}/{f.name}",
                            "thumb_url": f"/admin/chat/images/{session_id}/{img_id}_thumb.jpg",
                        }
                    )
                    break
            ocr = _pending_image_ocr.pop(img_id, None)
            if ocr:
                image_ocr_parts.append(ocr)
        if images_meta:
            extra_data_json = json.dumps({"images": images_meta}, ensure_ascii=False)

    # Build content: user text + OCR from images
    llm_content = msg_request.content
    if image_ocr_parts:
        ocr_block = "\n\n".join(f"[Текст с изображения]:\n{ocr}" for ocr in image_ocr_parts)
        llm_content = f"{msg_request.content}\n\n{ocr_block}" if msg_request.content else ocr_block

    user_msg = await chat_service.add_message(
        session_id, "user", llm_content, extra_data=extra_data_json
    )

    # Resolve RAG config (stays in router — depends on override/widget/mobile context)
    rag_mode, collection_ids = await _resolve_rag_config(
        session,
        msg_request.llm_override,
        msg_request.widget_instance_id,
        msg_request.mobile_instance_id,
    )

    # Delegate generation to ChatService facade
    facade = chat_service_facade or ChatServiceImpl(container)

    async def generate_stream():
        async for chunk in facade.stream_message(
            session_id,
            llm_content,
            llm_service=active_llm,
            session_data=session,
            user_msg=user_msg,
            system_prompt=custom_prompt,
            rag_mode=rag_mode,
            collection_ids=collection_ids,
        ):
            # Serialize StreamChunk to SSE event
            if chunk.get("done"):
                yield "data: [DONE]\n\n"
            else:
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

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
    user: User = Depends(require_permission("chat", "edit")),
):
    """Редактировать сообщение (non-destructive: creates new branch)"""
    container = get_container()
    session = await _check_write_access(session_id, user)

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
    edited_msg = await chat_service.edit_message(session_id, message_id, request.content)

    # Assistant edits: just save the new text, no LLM regeneration
    if message["role"] == "assistant":
        return {"message": edited_msg}

    # User edits: generate new LLM response for the edited message
    llm_service = container.llm_service
    if not llm_service:
        return {"message": edited_msg}

    rag_mode, collection_ids = await _resolve_rag_config(session)

    facade = chat_service_facade or ChatServiceImpl(container)
    try:
        assistant_msg = await facade.send_message(
            session_id,
            request.content,
            llm_service=llm_service,
            session_data=session,
            rag_mode=rag_mode,
            collection_ids=collection_ids,
            parent_id=edited_msg["id"],
        )
        return {"message": edited_msg, "response": assistant_msg}
    except Exception as e:
        logger.error(f"Chat edit regenerate error: {e}")
        return {"message": edited_msg, "error": str(e)}


@router.delete("/sessions/{session_id}/messages/{message_id}")
async def admin_delete_chat_message(
    session_id: str, message_id: str, user: User = Depends(require_permission("chat", "edit"))
):
    """Удалить сообщение и все последующие"""
    await _check_write_access(session_id, user)
    if not await chat_service.delete_message(session_id, message_id):
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "ok"}


@router.post("/sessions/{session_id}/messages/{message_id}/regenerate")
async def admin_regenerate_chat_response(
    session_id: str, message_id: str, user: User = Depends(require_permission("chat", "edit"))
):
    """Перегенерировать ответ (non-destructive: creates new branch)"""
    container = get_container()
    session = await _check_write_access(session_id, user)

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
        parent_msg = await chat_service.branch_regenerate(session_id, message_id)
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
                        await chat_service.branch_regenerate(session_id, next_msg["id"])
                break
        parent_id = message_id

    # Generate new response via facade
    user_content = target_msg["content"] if target_msg["role"] == "user" else ""
    rag_mode, collection_ids = await _resolve_rag_config(session)

    facade = chat_service_facade or ChatServiceImpl(container)
    try:
        assistant_msg = await facade.send_message(
            session_id,
            user_content,
            llm_service=llm_service,
            session_data=session,
            rag_mode=rag_mode,
            collection_ids=collection_ids,
            parent_id=parent_id,
        )
        return {"response": assistant_msg}
    except Exception as e:
        logger.error(f"Chat regenerate error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Summarize Endpoint ==============


@router.post("/sessions/{session_id}/messages/{message_id}/summarize")
async def admin_summarize_branch(
    session_id: str, message_id: str, user: User = Depends(require_permission("chat", "edit"))
):
    """Сгенерировать итоги ветки диалога и вернуть как markdown."""
    container = get_container()
    owner_id, ws_id = workspace_context(user, "chat")
    session = await chat_service.get_session(session_id, owner_id=owner_id, workspace_id=ws_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    llm_service = container.llm_service
    if not llm_service:
        raise HTTPException(status_code=503, detail="LLM service not available")

    # Get branch path from root to this message
    branch_messages = await chat_service.get_branch_path(session_id, message_id)
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


async def _get_branch_visible_ids(session_id: str, user: User) -> tuple[dict, Optional[set[str]]]:
    """Check session access and compute visible message IDs for branch endpoints.

    Returns (session_data, visible_ids). visible_ids is always None (full tree)
    for any user who has access to the session. Access check is done via get_session
    which filters by owner_id + workspace + shares.
    """
    owner_id, ws_id = workspace_context(user, "chat")
    session_data = await chat_service.get_session(session_id, owner_id=owner_id, workspace_id=ws_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")

    # All users with session access see the full branch tree
    return session_data, None


@router.get("/sessions/{session_id}/branches")
async def admin_get_branch_tree(
    session_id: str, user: User = Depends(require_permission("chat", "view"))
):
    """Получить дерево веток чата"""
    _, visible_ids = await _get_branch_visible_ids(session_id, user)
    branches = await chat_service.get_branch_tree(session_id, visible_ids=visible_ids)
    return {"branches": branches}


@router.post("/sessions/{session_id}/branches/switch")
async def admin_switch_branch(
    session_id: str,
    request: SwitchBranchRequest,
    user: User = Depends(require_permission("chat", "view")),
):
    """Переключить активную ветку"""
    _, visible_ids = await _get_branch_visible_ids(session_id, user)

    # For shared users, verify the target message is within the visible branch
    if visible_ids is not None and request.message_id not in visible_ids:
        raise HTTPException(status_code=403, detail="Message not in shared branch")

    success = await chat_service.switch_branch(session_id, request.message_id)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")

    # Frontend refetches the session + branches in parallel right after this
    # call, so re-querying them here just doubles the work and keeps the
    # connection open longer.
    return {"status": "ok"}


@router.post("/sessions/{session_id}/branches/new")
async def admin_new_branch(
    session_id: str,
    user: User = Depends(require_permission("chat", "edit")),
):
    """Начать новую ветку с чистого листа (деактивирует все сообщения)"""
    await _check_write_access(session_id, user)
    success = await chat_service.start_new_branch(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    session = await chat_service.get_session(session_id, workspace_id=user.workspace_id)
    sibling_info = await chat_service.get_sibling_info(session_id)
    if session:
        session["sibling_info"] = sibling_info
    return {"status": "ok", "session": session}


@router.put("/sessions/{session_id}/branches/{message_id}/rename")
async def admin_rename_branch(
    session_id: str,
    message_id: str,
    request: RenameBranchRequest,
    user: User = Depends(require_permission("chat", "edit")),
):
    """Переименовать ветку (не меняет контекст диалога)"""
    await _check_write_access(session_id, user)
    name = request.branch_name.strip()[:100]
    success = await chat_service.rename_branch(session_id, message_id, name)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "ok", "branch_name": name or None}


@router.get("/sessions/{session_id}/branches/search")
async def admin_search_branch_messages(
    session_id: str,
    q: str = Query("", min_length=1),
    match_case: bool = False,
    user: User = Depends(require_permission("chat", "view")),
):
    """Поиск по всем сообщениям сессии (включая неактивные ветки)"""
    owner_id, ws_id = workspace_context(user, "chat")
    session_data = await chat_service.get_session(session_id, owner_id=owner_id, workspace_id=ws_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")
    matches = await chat_service.search_messages(session_id, q, match_case)
    return {"matches": matches, "query": q, "total": len(matches)}


# ============== Sharing Endpoints ==============


@router.get("/sessions/{session_id}/shares")
async def admin_get_session_shares(
    session_id: str, user: User = Depends(require_permission("chat", "edit"))
):
    """Получить список шар для сессии (owner/admin)"""
    await _check_session_owner_or_admin(session_id, user)
    shares = await chat_share_service.get_shares(session_id)
    return {"shares": shares}


@router.post("/sessions/{session_id}/shares")
async def admin_share_session(
    session_id: str,
    request: ShareSessionRequest,
    user: User = Depends(require_permission("chat", "edit")),
):
    """Расшарить сессию пользователю (owner/admin, not guest)"""
    session_data = await _check_session_owner_or_admin(session_id, user)

    # Only share admin-source sessions
    if session_data.get("source") and session_data["source"] != "admin":
        raise HTTPException(status_code=400, detail="Only admin chats can be shared")

    if request.permission not in ("read", "write"):
        raise HTTPException(status_code=400, detail="Permission must be 'read' or 'write'")

    # Cannot share with yourself
    if request.user_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot share with yourself")

    # Snapshot current branch tip (last active message)
    active_messages = await chat_service.get_active_messages(session_id)
    branch_message_id = active_messages[-1]["id"] if active_messages else None

    share = await chat_share_service.add_share(
        session_id,
        request.user_id,
        request.permission,
        shared_by=user.id,
        branch_message_id=branch_message_id,
    )
    return {"share": share}


@router.put("/sessions/{session_id}/shares/{target_user_id}")
async def admin_update_session_share(
    session_id: str,
    target_user_id: int,
    request: UpdateShareRequest,
    user: User = Depends(require_permission("chat", "edit")),
):
    """Изменить permission шара (owner/admin)"""
    await _check_session_owner_or_admin(session_id, user)
    if request.permission not in ("read", "write"):
        raise HTTPException(status_code=400, detail="Permission must be 'read' or 'write'")
    ok = await chat_share_service.update_permission(session_id, target_user_id, request.permission)
    if not ok:
        raise HTTPException(status_code=404, detail="Share not found")
    return {"status": "ok"}


@router.delete("/sessions/{session_id}/shares/{target_user_id}")
async def admin_remove_session_share(
    session_id: str,
    target_user_id: int,
    user: User = Depends(require_permission("chat", "edit")),
):
    """Удалить шар (owner/admin)"""
    await _check_session_owner_or_admin(session_id, user)
    ok = await chat_share_service.remove_share(session_id, target_user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Share not found")
    return {"status": "ok"}


@router.post("/sessions/{session_id}/fork")
async def admin_fork_session(
    session_id: str,
    request: ForkSessionRequest,
    user: User = Depends(require_permission("chat", "edit")),
):
    """Форк сессии — глубокое копирование к себе (любой с доступом, not guest)"""
    # Verify the user has at least read access
    owner_id, ws_id = workspace_context(user, "chat")
    session_data = await chat_service.get_session(session_id, owner_id=owner_id, workspace_id=ws_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")

    new_session = await chat_share_service.fork_session(session_id, user.id, request.title)
    if not new_session:
        raise HTTPException(status_code=500, detail="Failed to fork session")
    return {"session": new_session}


@router.get("/shareable-users")
async def admin_get_shareable_users(
    include_self: bool = False,
    user: User = Depends(require_permission("chat", "view")),
):
    """Список пользователей для шаринга"""
    exclude_id = None if include_self else user.id
    users = await chat_share_service.list_shareable_users(exclude_user_id=exclude_id)
    return {"users": users}


# ============== Default Mobile Chat Endpoints ==============


class SetDefaultMobileRequest(BaseModel):
    user_ids: list[int]


@router.get("/sessions/{session_id}/default-mobile-users")
async def get_default_mobile_users(
    session_id: str,
    user: User = Depends(require_permission("chat", "edit")),
):
    """Get users who have this session as their default mobile chat."""
    users = await chat_share_service.get_default_mobile_users(session_id)
    return {"users": users}


@router.put("/sessions/{session_id}/default-mobile")
async def set_default_mobile_chat(
    session_id: str,
    req: SetDefaultMobileRequest,
    user: User = Depends(require_permission("chat", "edit")),
):
    """Set this session as default mobile chat for selected users.

    Clears previous defaults for each user before setting new ones.
    Auto-creates share if not exists.
    """
    results = []
    for uid in req.user_ids:
        share = await chat_share_service.set_default_mobile(session_id, uid, shared_by=user.id)
        results.append(share)
    return {"shares": results}


@router.delete("/sessions/{session_id}/default-mobile/{target_user_id}")
async def unset_default_mobile_chat(
    session_id: str,
    target_user_id: int,
    user: User = Depends(require_permission("chat", "edit")),
):
    """Remove default mobile flag for a user on this session."""
    ok = await chat_share_service.unset_default_mobile(session_id, target_user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Share not found")
    return {"status": "ok"}


@router.get("/my-default-mobile-session")
async def get_my_default_mobile_session(
    user: User = Depends(require_permission("chat", "view")),
):
    """Get the default mobile session for the current user."""
    session_id = await chat_share_service.get_user_default_mobile_session(user.id)
    return {"session_id": session_id}


# ============== Image Endpoints ==============


@router.post("/sessions/{session_id}/upload-image")
async def admin_upload_chat_file(
    session_id: str,
    file: UploadFile = File(...),
    user: User = Depends(require_permission("chat", "edit")),
):
    """Upload a file (image or document) for a chat session, extract text, return metadata."""
    from modules.chat.image_service import ALLOWED_MIME_TYPES, MAX_FILE_SIZE, upload_file

    await _check_write_access(session_id, user)

    content_type = file.content_type or "application/octet-stream"
    file_data = await file.read()
    original_name = file.filename or "file"

    if len(file_data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 300MB)")

    # Allow by MIME type or by known extension
    from pathlib import Path as _Path

    ext = _Path(original_name).suffix.lower()
    text_exts = {".txt", ".csv", ".md", ".json", ".xml", ".html", ".log", ".yaml", ".yml"}
    if content_type not in ALLOWED_MIME_TYPES and ext not in text_exts:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {content_type}")

    try:
        file_meta = await upload_file(session_id, file_data, content_type, original_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Cache extracted text for when the message is sent
    if file_meta.get("ocr_text"):
        _pending_image_ocr[file_meta["id"]] = file_meta["ocr_text"]

    return {
        "image": {
            "id": file_meta["id"],
            "url": f"/admin/chat/images/{session_id}/{file_meta['filename']}",
            "thumb_url": f"/admin/chat/images/{session_id}/{file_meta['id']}_thumb.jpg"
            if file_meta.get("is_image")
            else None,
            "ocr_text": file_meta.get("ocr_text"),
            "width": file_meta.get("width", 0),
            "height": file_meta.get("height", 0),
            "original_name": file_meta["original_name"],
            "size": file_meta["size"],
            "mime_type": file_meta["mime_type"],
            "is_image": file_meta.get("is_image", False),
        }
    }


@router.get("/images/{session_id}/{filename}")
async def serve_chat_image(
    session_id: str,
    filename: str,
    token: Optional[str] = None,
    user: Optional[User] = Depends(get_optional_user),
):
    """Serve an uploaded chat file (image or document), auth-gated.

    Accepts auth via the Authorization header OR a ``?token=`` query param —
    ``<img src>`` / ``<a download>`` requests can't send an Authorization header,
    so the frontend appends the JWT as a query param for these URLs.
    """
    from modules.chat.image_service import get_image_path

    # Header path (get_optional_user) doesn't load permissions; the token path does.
    if user is not None:
        user.permissions = await get_user_permissions(user)
    elif token:
        user = await resolve_user_from_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not level_gte(user.permissions.get("chat", ""), "view"):
        raise HTTPException(status_code=403, detail="Permission denied: requires chat:view")

    path = get_image_path(session_id, filename)
    if not path:
        raise HTTPException(status_code=404, detail="Image not found")

    # Determine media type
    import mimetypes

    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

    return FileResponse(path, media_type=media_type)


# ============== Session-scoped System Prompts ==============
#
# Each chat session can have several named system prompts; exactly one is
# active. Activation copies the prompt's content into ChatSession.system_prompt
# so the existing streaming pipeline picks it up — switching prompt changes
# the assistant's role while keeping conversation history intact.


class _SessionPromptCreate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    is_active: Optional[bool] = None


class _SessionPromptUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None


async def _sync_session_system_prompt(session, content: Optional[str]) -> None:
    session.system_prompt = content
    session.updated = datetime.utcnow()


@router.get("/sessions/{session_id}/prompts")
async def admin_list_session_prompts(
    session_id: str, user: User = Depends(require_permission("chat", "view"))
):
    """List named system prompts for a chat session."""
    from sqlalchemy import select

    from db.database import get_session_context
    from modules.chat.models import ChatSessionPrompt

    owner_id, ws_id = workspace_context(user, "chat")
    session_data = await chat_service.get_session(session_id, owner_id=owner_id, workspace_id=ws_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")

    async with get_session_context() as db:
        rows = (
            (
                await db.execute(
                    select(ChatSessionPrompt)
                    .where(ChatSessionPrompt.session_id == session_id)
                    .order_by(ChatSessionPrompt.created.asc())
                )
            )
            .scalars()
            .all()
        )
        return {"prompts": [p.to_dict() for p in rows]}


@router.post("/sessions/{session_id}/prompts")
async def admin_create_session_prompt(
    session_id: str,
    request: _SessionPromptCreate,
    user: User = Depends(require_permission("chat", "edit")),
):
    """Create a new named prompt for a chat session.

    The first prompt is automatically activated; if the session already has a
    `system_prompt` and the request omits content, it is preserved as the
    initial content of that first prompt (so the user does not lose their
    existing prompt by clicking "+ new prompt").
    """
    from sqlalchemy import select

    from db.database import get_session_context
    from modules.chat.models import ChatSession, ChatSessionPrompt

    await _check_write_access(session_id, user)

    async with get_session_context() as db:
        session_obj = (
            await db.execute(select(ChatSession).where(ChatSession.id == session_id))
        ).scalar_one_or_none()
        if session_obj is None:
            raise HTTPException(status_code=404, detail="Session not found")

        existing = (
            (
                await db.execute(
                    select(ChatSessionPrompt).where(ChatSessionPrompt.session_id == session_id)
                )
            )
            .scalars()
            .all()
        )
        is_first = len(existing) == 0

        content = request.content
        if is_first and not content and session_obj.system_prompt:
            content = session_obj.system_prompt
        if content is None:
            content = ""

        make_active = bool(request.is_active) if request.is_active is not None else is_first
        if make_active:
            for p in existing:
                p.is_active = False

        prompt = ChatSessionPrompt(
            session_id=session_id,
            name=(request.name or None),
            content=content,
            is_active=make_active,
        )
        db.add(prompt)
        await db.flush()

        if make_active:
            await _sync_session_system_prompt(session_obj, content)

        await db.commit()
        await db.refresh(prompt)
        return {"prompt": prompt.to_dict()}


@router.patch("/sessions/{session_id}/prompts/{prompt_id}")
async def admin_update_session_prompt(
    session_id: str,
    prompt_id: int,
    request: _SessionPromptUpdate,
    user: User = Depends(require_permission("chat", "edit")),
):
    """Update name and/or content of a session prompt. Syncs session.system_prompt if active."""
    from sqlalchemy import select

    from db.database import get_session_context
    from modules.chat.models import ChatSession, ChatSessionPrompt

    await _check_write_access(session_id, user)

    payload = request.model_dump(exclude_unset=True)

    async with get_session_context() as db:
        prompt = (
            await db.execute(
                select(ChatSessionPrompt).where(
                    ChatSessionPrompt.id == prompt_id,
                    ChatSessionPrompt.session_id == session_id,
                )
            )
        ).scalar_one_or_none()
        if prompt is None:
            raise HTTPException(status_code=404, detail="Prompt not found")

        if "name" in payload:
            value = payload["name"]
            prompt.name = value if value else None
        content_changed = False
        if "content" in payload:
            new_content = payload["content"] or ""
            content_changed = new_content != (prompt.content or "")
            prompt.content = new_content

        if prompt.is_active and content_changed:
            session_obj = (
                await db.execute(select(ChatSession).where(ChatSession.id == session_id))
            ).scalar_one_or_none()
            if session_obj is not None:
                await _sync_session_system_prompt(session_obj, prompt.content)

        await db.commit()
        await db.refresh(prompt)
        return {"prompt": prompt.to_dict()}


@router.post("/sessions/{session_id}/prompts/{prompt_id}/activate")
async def admin_activate_session_prompt(
    session_id: str,
    prompt_id: int,
    user: User = Depends(require_permission("chat", "edit")),
):
    """Activate a prompt — makes it the session's system prompt."""
    from sqlalchemy import select, update

    from db.database import get_session_context
    from modules.chat.models import ChatSession, ChatSessionPrompt

    await _check_write_access(session_id, user)

    async with get_session_context() as db:
        prompt = (
            await db.execute(
                select(ChatSessionPrompt).where(
                    ChatSessionPrompt.id == prompt_id,
                    ChatSessionPrompt.session_id == session_id,
                )
            )
        ).scalar_one_or_none()
        if prompt is None:
            raise HTTPException(status_code=404, detail="Prompt not found")

        await db.execute(
            update(ChatSessionPrompt)
            .where(
                ChatSessionPrompt.session_id == session_id,
                ChatSessionPrompt.id != prompt_id,
            )
            .values(is_active=False)
        )
        prompt.is_active = True

        session_obj = (
            await db.execute(select(ChatSession).where(ChatSession.id == session_id))
        ).scalar_one_or_none()
        if session_obj is not None:
            await _sync_session_system_prompt(session_obj, prompt.content or "")

        await db.commit()
        await db.refresh(prompt)
        return {"prompt": prompt.to_dict()}


@router.delete("/sessions/{session_id}/prompts/{prompt_id}")
async def admin_delete_session_prompt(
    session_id: str,
    prompt_id: int,
    user: User = Depends(require_permission("chat", "edit")),
):
    """Delete a prompt. If it was active, promote the most recent remaining one."""
    from sqlalchemy import select

    from db.database import get_session_context
    from modules.chat.models import ChatSession, ChatSessionPrompt

    await _check_write_access(session_id, user)

    async with get_session_context() as db:
        prompt = (
            await db.execute(
                select(ChatSessionPrompt).where(
                    ChatSessionPrompt.id == prompt_id,
                    ChatSessionPrompt.session_id == session_id,
                )
            )
        ).scalar_one_or_none()
        if prompt is None:
            raise HTTPException(status_code=404, detail="Prompt not found")

        was_active = prompt.is_active
        await db.delete(prompt)
        await db.flush()

        if was_active:
            replacement = (
                await db.execute(
                    select(ChatSessionPrompt)
                    .where(ChatSessionPrompt.session_id == session_id)
                    .order_by(ChatSessionPrompt.created.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            session_obj = (
                await db.execute(select(ChatSession).where(ChatSession.id == session_id))
            ).scalar_one_or_none()
            if replacement is not None:
                replacement.is_active = True
                if session_obj is not None:
                    await _sync_session_system_prompt(session_obj, replacement.content or "")
            elif session_obj is not None:
                await _sync_session_system_prompt(session_obj, None)

        await db.commit()
        return {"status": "deleted"}
