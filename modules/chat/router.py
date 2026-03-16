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
from app.utils.tokens import count_message_tokens, get_context_window, trim_messages
from auth_manager import User, require_permission, user_has_level, workspace_context
from cloud_llm_service import CloudLLMService
from modules.channels.mobile.service import mobile_app_instance_service
from modules.channels.telegram.service import bot_instance_service
from modules.channels.whatsapp.service import whatsapp_instance_service
from modules.channels.widget.service import widget_instance_service
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

# Agentic RAG: LLM decides when to search the knowledge base
KNOWLEDGE_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "knowledge_search",
        "description": (
            "Search the knowledge base for relevant information. "
            "Use when the user asks something that might be answered by documentation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query. Be specific."}
            },
            "required": ["query"],
        },
    },
}
MAX_TOOL_ITERATIONS = 5

# Temporary cache for OCR text from uploaded images (upload → send are two separate requests)
_pending_image_ocr: dict[str, str] = {}

_AGENTIC_RAG_SUFFIX = (
    "\n\nУ тебя есть инструмент knowledge_search для поиска по базе знаний. "
    "Используй его когда вопрос связан с документацией или требует фактических данных. "
    "Можешь вызвать несколько раз с разными запросами. "
    "Не выдумывай — если не нашёл информацию, честно скажи."
)


def _inject_context_files(prompt: str | None, session: dict) -> str | None:
    """Inject context file contents into system prompt if session has any."""
    context_files = session.get("context_files")
    if not context_files:
        return prompt
    files_text = "\n\n".join(f"# {f['name']}\n{f['content']}" for f in context_files)
    base = prompt or _DEFAULT_RAG_PROMPT
    return f"{base}\n\n--- Прикреплённые файлы ---\n{files_text}"


def _finalize_prompt(prompt: str | None, agentic_rag: bool = False) -> str:
    """Add suffix to system prompt: agentic RAG instructions or anti-tool-call guard."""
    base = prompt or _DEFAULT_RAG_PROMPT
    return base + (_AGENTIC_RAG_SUFFIX if agentic_rag else _NO_TOOLS_SUFFIX)


def _should_use_agentic_rag(
    llm_service, rag_mode: str, collection_ids: list[int], wiki_rag
) -> bool:
    """Check if agentic RAG loop should be used instead of one-shot injection."""
    if rag_mode == "none" or not collection_ids or not wiki_rag:
        return False
    # Check provider supports tools (CloudLLMService wraps provider, VLLMLLMService has it directly)
    if getattr(llm_service, "supports_tools", False):
        return True
    return hasattr(llm_service, "provider") and getattr(
        llm_service.provider, "supports_tools", False
    )


def _execute_knowledge_search(wiki_rag, query: str, collection_ids: list[int]) -> str:
    """Execute a knowledge base search and return results text."""
    if len(collection_ids) == 1:
        return wiki_rag.retrieve(query, top_k=5, max_chars=3000, collection_id=collection_ids[0])
    return wiki_rag.retrieve_multi(query, collection_ids, top_k=5, max_chars=3000)


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
        wiki_context = wiki_rag.retrieve(
            user_content, top_k=7, max_chars=4000, collection_id=collection_ids[0]
        )
    else:
        wiki_context = wiki_rag.retrieve_multi(
            user_content, collection_ids, top_k=7, max_chars=4000
        )

    logger.info(
        f"RAG inject: context found={bool(wiki_context)}, len={len(wiki_context) if wiki_context else 0}"
    )

    base = base_prompt or _DEFAULT_RAG_PROMPT
    if wiki_context:
        rag_instruction = (
            "\n\n--- КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ (обязательно к использованию) ---\n"
            "Ниже приведена релевантная информация из базы знаний. "
            "ОБЯЗАТЕЛЬНО используй эти данные при ответе. "
            "Если информация ниже отвечает на вопрос пользователя — ответь на основе неё. "
            "НЕ выдумывай информацию, которой нет в контексте ниже.\n"
        )
        return f"{base}{rag_instruction}\n{wiki_context}"

    # RAG search returned nothing — instruct LLM not to hallucinate
    no_context_instruction = (
        "\n\n--- ВАЖНО ---\n"
        "По данному запросу в базе знаний не найдено релевантной информации. "
        "НЕ выдумывай ответ. Если ты не уверен в точности информации — "
        "честно скажи, что не нашёл данных в базе знаний, и предложи "
        "обратиться к менеджеру или уточнить вопрос.\n"
    )
    return f"{base}{no_context_instruction}"


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
    knowledge_collection_ids: Optional[list[int]] = None
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
    image_ids: Optional[list[str]] = None
    llm_override: Optional[LLMOverrideConfig] = None
    widget_instance_id: Optional[str] = None
    mobile_instance_id: Optional[str] = None


class EditMessageRequest(BaseModel):
    content: str


class SwitchBranchRequest(BaseModel):
    message_id: str


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

    def _enrich(sessions_list: list[dict], share_counts: dict[str, int]) -> list[dict]:
        for s in sessions_list:
            sid = s.get("id", "")
            s_owner = s.get("owner_id")
            if sid in shared_perms and s_owner != user.id and s_owner is not None:
                s["is_shared_with_me"] = True
                s["share_permission"] = shared_perms[sid]
            else:
                s["is_shared_with_me"] = False
                s["share_permission"] = "owner"
            s["share_count"] = share_counts.get(sid, 0)
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

    # Auto-apply instance system_prompt if not explicitly provided
    system_prompt = request.system_prompt
    if request.source == "widget" and request.source_id and not system_prompt:
        widget = await widget_instance_service.get_instance(request.source_id)
        if widget and widget.get("system_prompt"):
            system_prompt = widget["system_prompt"]
    elif request.source == "mobile" and request.source_id and not system_prompt:
        mobile_inst = await mobile_app_instance_service.get_instance(request.source_id)
        if mobile_inst and mobile_inst.get("system_prompt"):
            system_prompt = mobile_inst["system_prompt"]

    session = await chat_service.create_session(
        request.title,
        system_prompt,
        request.source,
        request.source_id,
        owner_id=owner_id,
        rag_mode=request.rag_mode,
        knowledge_collection_id=request.knowledge_collection_id,
        workspace_id=ws_id,
    )
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
    is_owner = (
        user_has_level(user, "chat", "manage")
        or session_owner_id == user.id
        or session_owner_id is None
    )
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

    # Получаем историю для LLM
    # Session prompt takes priority; fallback to LLM service default
    default_prompt = session.get("system_prompt")
    if not default_prompt and hasattr(llm_service, "get_system_prompt"):
        default_prompt = llm_service.get_system_prompt()

    # RAG: inject relevant wiki context based on rag_mode
    rag_mode, collection_ids = await _resolve_rag_config(session, msg_request.llm_override)
    wiki_rag = container.wiki_rag_service
    use_agentic = _should_use_agentic_rag(llm_service, rag_mode, collection_ids, wiki_rag)

    if not use_agentic:
        default_prompt = _inject_rag_context(
            wiki_rag, msg_request.content, default_prompt, rag_mode, collection_ids
        )

    # Inject context files
    default_prompt = _inject_context_files(default_prompt, session)

    messages = await chat_service.get_messages_for_llm(
        session_id, _finalize_prompt(default_prompt, agentic_rag=use_agentic)
    )

    # Trim to fit context window
    model = _get_model_name(llm_service)
    messages, _ = _trim_and_log(messages, model, session_id)

    # Генерируем ответ
    try:
        if use_agentic:
            # Agentic RAG loop (non-streaming)
            tools = [KNOWLEDGE_SEARCH_TOOL]
            loop_messages = list(messages)
            response_text = ""

            for _iteration in range(MAX_TOOL_ITERATIONS):
                result = llm_service.generate_response_from_messages(
                    loop_messages, stream=False, tools=tools
                )
                if isinstance(result, str):
                    response_text = result
                    break
                # dict with tool_calls
                tool_calls = result.get("tool_calls")
                if not tool_calls:
                    response_text = (result.get("content") or "").strip()
                    break

                loop_messages.append(result)  # assistant message with tool_calls
                for tc in tool_calls:
                    if tc["function"]["name"] != "knowledge_search":
                        continue
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    query = args.get("query", "")
                    search_result = _execute_knowledge_search(wiki_rag, query, collection_ids)
                    loop_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": search_result or "Ничего не найдено в базе знаний.",
                        }
                    )
        else:
            response_text = llm_service.generate_response_from_messages(messages, stream=False)
            if hasattr(response_text, "__iter__") and not isinstance(response_text, str):
                response_text = "".join(response_text)

        assistant_msg = await chat_service.add_message(session_id, "assistant", response_text)
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

    # Получаем историю для LLM
    # Priority: widget prompt > session prompt > LLM service default
    default_prompt = custom_prompt or session.get("system_prompt")
    if not default_prompt and hasattr(active_llm, "get_system_prompt"):
        default_prompt = active_llm.get_system_prompt()

    # RAG: inject relevant wiki context based on rag_mode
    rag_mode, collection_ids = await _resolve_rag_config(
        session,
        msg_request.llm_override,
        msg_request.widget_instance_id,
        msg_request.mobile_instance_id,
    )
    wiki_rag = container.wiki_rag_service
    use_agentic = _should_use_agentic_rag(active_llm, rag_mode, collection_ids, wiki_rag)

    if not use_agentic:
        # One-shot RAG: inject context into prompt (existing behavior)
        default_prompt = _inject_rag_context(
            wiki_rag, msg_request.content, default_prompt, rag_mode, collection_ids
        )

    # Inject context files
    default_prompt = _inject_context_files(default_prompt, session)

    messages = await chat_service.get_messages_for_llm(
        session_id, _finalize_prompt(default_prompt, agentic_rag=use_agentic)
    )

    # Trim to fit context window
    model = _get_model_name(active_llm)
    messages, was_trimmed = _trim_and_log(messages, model, session_id)

    async def generate_stream():
        full_response = []
        try:
            # Отправляем сообщение пользователя
            yield f"data: {json.dumps({'type': 'user_message', 'message': user_msg}, ensure_ascii=False)}\n\n"

            if use_agentic:
                # Agentic RAG loop: LLM decides when to search
                tools = [KNOWLEDGE_SEARCH_TOOL]
                loop_messages = list(messages)

                for _iteration in range(MAX_TOOL_ITERATIONS):
                    content_chunks = []
                    tool_calls_result = None

                    for event in active_llm.generate_response_from_messages(
                        loop_messages, stream=True, tools=tools
                    ):
                        if isinstance(event, dict):
                            if event["type"] == "content":
                                content_chunks.append(event["content"])
                                full_response.append(event["content"])
                                yield f"data: {json.dumps({'type': 'chunk', 'content': event['content']}, ensure_ascii=False)}\n\n"
                            elif event["type"] == "tool_calls":
                                tool_calls_result = event["tool_calls"]
                        else:
                            # Safety fallback: plain str from provider
                            full_response.append(event)
                            yield f"data: {json.dumps({'type': 'chunk', 'content': event}, ensure_ascii=False)}\n\n"

                    if not tool_calls_result:
                        break  # LLM answered with text, done

                    # Execute tool calls and feed results back
                    assistant_content = "".join(content_chunks) or None
                    loop_messages.append(
                        {
                            "role": "assistant",
                            "content": assistant_content,
                            "tool_calls": tool_calls_result,
                        }
                    )

                    for tc in tool_calls_result:
                        fn_name = tc["function"]["name"]
                        if fn_name != "knowledge_search":
                            continue
                        try:
                            args = json.loads(tc["function"]["arguments"])
                        except json.JSONDecodeError:
                            args = {}
                        query = args.get("query", "")
                        yield f"data: {json.dumps({'type': 'tool_start', 'name': fn_name, 'query': query}, ensure_ascii=False)}\n\n"

                        result = _execute_knowledge_search(wiki_rag, query, collection_ids)
                        found = bool(result and result.strip())
                        yield f"data: {json.dumps({'type': 'tool_end', 'name': fn_name, 'found': found}, ensure_ascii=False)}\n\n"

                        loop_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": result or "Ничего не найдено в базе знаний.",
                            }
                        )
            else:
                # One-shot: existing streaming path
                for chunk in active_llm.generate_response_from_messages(messages, stream=True):
                    full_response.append(chunk)
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"

            # Сохраняем полный ответ
            response_text = "".join(full_response)
            assistant_msg = await chat_service.add_message(session_id, "assistant", response_text)

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

    default_prompt = session.get("system_prompt")
    if not default_prompt and hasattr(llm_service, "get_system_prompt"):
        default_prompt = llm_service.get_system_prompt()

    # RAG: inject relevant wiki context based on rag_mode
    rag_mode, collection_ids = await _resolve_rag_config(session)
    wiki_rag = container.wiki_rag_service
    use_agentic = _should_use_agentic_rag(llm_service, rag_mode, collection_ids, wiki_rag)

    if not use_agentic:
        default_prompt = _inject_rag_context(
            wiki_rag, request.content, default_prompt, rag_mode, collection_ids
        )

    # Inject context files
    default_prompt = _inject_context_files(default_prompt, session)

    messages = await chat_service.get_messages_for_llm(
        session_id, _finalize_prompt(default_prompt, agentic_rag=use_agentic)
    )

    # Trim to fit context window
    model = _get_model_name(llm_service)
    messages, _ = _trim_and_log(messages, model, session_id)

    try:
        if use_agentic:
            tools = [KNOWLEDGE_SEARCH_TOOL]
            loop_messages = list(messages)
            response_text = ""

            for _iteration in range(MAX_TOOL_ITERATIONS):
                result = llm_service.generate_response_from_messages(
                    loop_messages, stream=False, tools=tools
                )
                if isinstance(result, str):
                    response_text = result
                    break
                tool_calls = result.get("tool_calls")
                if not tool_calls:
                    response_text = (result.get("content") or "").strip()
                    break
                loop_messages.append(result)
                for tc in tool_calls:
                    if tc["function"]["name"] != "knowledge_search":
                        continue
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    query = args.get("query", "")
                    search_result = _execute_knowledge_search(wiki_rag, query, collection_ids)
                    loop_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": search_result or "Ничего не найдено в базе знаний.",
                        }
                    )
        else:
            response_text = llm_service.generate_response_from_messages(messages, stream=False)
            if hasattr(response_text, "__iter__") and not isinstance(response_text, str):
                response_text = "".join(response_text)

        # Add response as child of the new edited message
        assistant_msg = await chat_service.add_message(
            session_id, "assistant", response_text, parent_id=edited_msg["id"]
        )
        return {"message": edited_msg, "response": assistant_msg}

    except Exception as e:
        logger.error(f"❌ Chat regenerate error: {e}")
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

    # Generate new response
    default_prompt = session.get("system_prompt")
    if not default_prompt and hasattr(llm_service, "get_system_prompt"):
        default_prompt = llm_service.get_system_prompt()

    # RAG: inject relevant wiki context based on rag_mode
    user_content = target_msg["content"] if target_msg["role"] == "user" else ""
    rag_mode, collection_ids = await _resolve_rag_config(session)
    wiki_rag = container.wiki_rag_service
    use_agentic = _should_use_agentic_rag(llm_service, rag_mode, collection_ids, wiki_rag)

    if not use_agentic:
        default_prompt = _inject_rag_context(
            wiki_rag, user_content, default_prompt, rag_mode, collection_ids
        )

    # Inject context files
    default_prompt = _inject_context_files(default_prompt, session)

    llm_messages = await chat_service.get_messages_for_llm(
        session_id, _finalize_prompt(default_prompt, agentic_rag=use_agentic)
    )

    # Trim to fit context window
    model = _get_model_name(llm_service)
    llm_messages, _ = _trim_and_log(llm_messages, model, session_id)

    try:
        if use_agentic:
            tools = [KNOWLEDGE_SEARCH_TOOL]
            loop_messages = list(llm_messages)
            response_text = ""

            for _iteration in range(MAX_TOOL_ITERATIONS):
                result = llm_service.generate_response_from_messages(
                    loop_messages, stream=False, tools=tools
                )
                if isinstance(result, str):
                    response_text = result
                    break
                tool_calls = result.get("tool_calls")
                if not tool_calls:
                    response_text = (result.get("content") or "").strip()
                    break
                loop_messages.append(result)
                for tc in tool_calls:
                    if tc["function"]["name"] != "knowledge_search":
                        continue
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    query = args.get("query", "")
                    search_result = _execute_knowledge_search(wiki_rag, query, collection_ids)
                    loop_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": search_result or "Ничего не найдено в базе знаний.",
                        }
                    )
        else:
            response_text = llm_service.generate_response_from_messages(llm_messages, stream=False)
            if hasattr(response_text, "__iter__") and not isinstance(response_text, str):
                response_text = "".join(response_text)

        assistant_msg = await chat_service.add_message(
            session_id, "assistant", response_text, parent_id=parent_id
        )
        return {"response": assistant_msg}

    except Exception as e:
        logger.error(f"❌ Chat regenerate error: {e}")
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

    Returns (session_data, visible_ids). visible_ids is None for owner/admin (full tree).
    """
    owner_id, ws_id = workspace_context(user, "chat")
    session_data = await chat_service.get_session(session_id, owner_id=owner_id, workspace_id=ws_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")

    visible_ids: Optional[set[str]] = None
    if not user_has_level(user, "chat", "manage"):
        session_owner = session_data.get("owner_id")
        if session_owner not in (user.id, None):
            # Shared user — restrict to shared branch
            share = await chat_share_service.get_user_share(session_id, user.id)
            if share and share.get("branch_message_id"):
                visible_ids = await chat_service.compute_branch_visible_ids(
                    session_id, share["branch_message_id"]
                )

    return session_data, visible_ids


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

    # Return updated session
    session = await chat_service.get_session(session_id, workspace_id=user.workspace_id)
    if session:
        sibling_info = await chat_service.get_sibling_info(session_id)
        session["sibling_info"] = sibling_info
    return {"status": "ok", "session": session}


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
async def admin_get_shareable_users(user: User = Depends(require_permission("chat", "view"))):
    """Список пользователей для шаринга"""
    users = await chat_share_service.list_shareable_users(exclude_user_id=user.id)
    return {"users": users}


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
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

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
    user: User = Depends(require_permission("chat", "view")),
):
    """Serve an uploaded chat image (auth-gated)."""
    from modules.chat.image_service import get_image_path

    path = get_image_path(session_id, filename)
    if not path:
        raise HTTPException(status_code=404, detail="Image not found")

    # Determine media type
    import mimetypes

    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

    return FileResponse(path, media_type=media_type)
