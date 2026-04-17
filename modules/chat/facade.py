"""ChatService facade — unified entry point for chat CRUD + LLM generation.

Implements the ``ChatService`` Protocol from ``modules.chat.protocols``.
Delegates to existing services (Strangler Fig pattern):
- Session/message CRUD  -> ``ChatService`` (modules/chat/service.py)
- Sharing               -> ``ChatShareService`` (modules/chat/service.py)
- LLM generation        -> underlying LLM service via ``ServiceContainer``
- RAG / tool execution  -> ``wiki_rag_service``, ``web_search_service``

The router stays responsible for HTTP concerns (auth, rate limiting,
request parsing, LLM backend resolution, image uploads). The facade
owns the core flow: prompt assembly -> RAG -> LLM call -> save response.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from modules.chat.schemas import ShareInfo, StreamChunk


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.dependencies import ServiceContainer

logger = logging.getLogger(__name__)

# Max agentic tool-call iterations (matches router constant)
MAX_TOOL_ITERATIONS = 10

# Default RAG system prompt
_DEFAULT_RAG_PROMPT = (
    "Ты — ИИ-секретарь. Отвечай на вопросы пользователя кратко и по делу, "
    "используя предоставленную документацию. Отвечай на языке пользователя."
)

_NO_TOOLS_SUFFIX = (
    "\n\nВАЖНО: Ты — чат-бот без доступа к инструментам, файлам и командам. "
    "НИКОГДА не генерируй вызовы функций, tool_use, function_calls, "
    "filesystem, code execution или любые блоки вида `command { ... }`. "
    "Отвечай только обычным текстом. Используй markdown для форматирования."
)

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

# Fallback persona for sessions without an explicit system_prompt — platform
# agent that helps users configure their own assistants. Loaded once from
# /opt/ai-secretary/prompts/platform-agent.md (overridable via env var).
_PLATFORM_AGENT_PROMPT: str | None = None
_PLATFORM_AGENT_LOADED = False


def _load_platform_agent_prompt() -> str | None:
    global _PLATFORM_AGENT_PROMPT, _PLATFORM_AGENT_LOADED
    if _PLATFORM_AGENT_LOADED:
        return _PLATFORM_AGENT_PROMPT
    path = Path(
        os.getenv("PLATFORM_AGENT_PROMPT_FILE", "/opt/ai-secretary/prompts/platform-agent.md")
    )
    try:
        text = path.read_text(encoding="utf-8").strip()
        _PLATFORM_AGENT_PROMPT = text or None
    except OSError as exc:
        logger.warning("Platform-agent prompt file not loaded (%s): %s", path, exc)
        _PLATFORM_AGENT_PROMPT = None
    _PLATFORM_AGENT_LOADED = True
    return _PLATFORM_AGENT_PROMPT

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

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the internet for current information. "
            "Use when the user asks about recent events, prices, weather, news, "
            "or anything that requires up-to-date data from the web."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query in the language of the user's question.",
                }
            },
            "required": ["query"],
        },
    },
}


# ---------------------------------------------------------------------------
# Helper functions (extracted from router)
# ---------------------------------------------------------------------------


def _supports_tools(llm_service) -> bool:
    """Check if the LLM provider supports tool calling."""
    if getattr(llm_service, "supports_tools", False):
        return True
    return hasattr(llm_service, "provider") and getattr(
        llm_service.provider, "supports_tools", False
    )


def _should_use_agentic_rag(
    llm_service, rag_mode: str, collection_ids: list[int], wiki_rag
) -> bool:
    """Check if agentic RAG loop should be used instead of one-shot injection."""
    if rag_mode == "none" or not collection_ids or not wiki_rag:
        return False
    return _supports_tools(llm_service)


def _build_tools(use_agentic: bool, use_web_search: bool) -> list[dict]:
    """Build the tools list based on enabled features."""
    tools: list[dict] = []
    if use_agentic:
        tools.append(KNOWLEDGE_SEARCH_TOOL)
    if use_web_search:
        tools.append(WEB_SEARCH_TOOL)
    return tools


def _finalize_prompt(
    prompt: str | None, agentic_rag: bool = False, web_search: bool = False
) -> str:
    """Add suffix to system prompt."""
    base = prompt or _DEFAULT_RAG_PROMPT
    if not agentic_rag and not web_search:
        return base + _NO_TOOLS_SUFFIX
    result = base
    if agentic_rag:
        result += _AGENTIC_RAG_SUFFIX
    if web_search:
        result += _WEB_SEARCH_SUFFIX
    return result


def _inject_context_files(prompt: str | None, session: dict) -> str | None:
    """Inject context file contents into system prompt if session has any."""
    context_files = session.get("context_files")
    if not context_files:
        return prompt
    files_text = "\n\n".join(f"# {f['name']}\n{f['content']}" for f in context_files)
    base = prompt or _DEFAULT_RAG_PROMPT
    return f"{base}\n\n--- Прикреплённые файлы ---\n{files_text}"


def _execute_knowledge_search(wiki_rag, query: str, collection_ids: list[int]) -> str:
    """Execute a knowledge base search (sync)."""
    if len(collection_ids) == 1:
        return wiki_rag.retrieve(query, top_k=5, max_chars=3000, collection_id=collection_ids[0])
    return wiki_rag.retrieve_multi(query, collection_ids, top_k=5, max_chars=3000)


async def _execute_knowledge_search_async(wiki_rag, query: str, collection_ids: list[int]) -> str:
    """Execute knowledge search with vector search support (async)."""
    if not wiki_rag.vector_search_available:
        return await asyncio.to_thread(_execute_knowledge_search, wiki_rag, query, collection_ids)

    if len(collection_ids) == 1:
        return await wiki_rag.retrieve_async(
            query, top_k=5, max_chars=3000, collection_id=collection_ids[0]
        )
    return await wiki_rag.retrieve_multi_async(query, collection_ids, top_k=5, max_chars=3000)


def _execute_tool_call(
    fn_name: str,
    args: dict,
    wiki_rag,
    collection_ids: list[int],
) -> tuple[str, bool]:
    """Execute a tool call and return (result_text, found)."""
    if fn_name == "knowledge_search":
        query = args.get("query", "")
        if not query:
            return "Пустой поисковый запрос.", False
        result = _execute_knowledge_search(wiki_rag, query, collection_ids)
        found = bool(result and result.strip())
        return result or "Ничего не найдено в базе знаний.", found
    elif fn_name == "web_search":
        query = args.get("query", "")
        if not query:
            return "Пустой поисковый запрос.", False
        from modules.search.service import web_search_service

        result = web_search_service.search(query, max_results=5)
        found = bool(result and "No web results" not in result and "failed" not in result)
        return result, found
    else:
        return f"Неизвестный инструмент: {fn_name}", False


def _inject_rag_context(
    wiki_rag,
    user_content: str,
    base_prompt: str | None,
    rag_mode: str,
    collection_ids: list[int],
) -> str | None:
    """Inject RAG context into system prompt (sync, one-shot mode)."""
    if not wiki_rag or not user_content or rag_mode == "none" or not collection_ids:
        return base_prompt

    if len(collection_ids) == 1:
        wiki_context = wiki_rag.retrieve(
            user_content, top_k=7, max_chars=4000, collection_id=collection_ids[0]
        )
    else:
        wiki_context = wiki_rag.retrieve_multi(
            user_content, collection_ids, top_k=7, max_chars=4000
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

    no_context_instruction = (
        "\n\n--- ВАЖНО ---\n"
        "По данному запросу в базе знаний не найдено релевантной информации. "
        "НЕ выдумывай ответ. Если ты не уверен в точности информации — "
        "честно скажи, что не нашёл данных в базе знаний, и предложи "
        "обратиться к менеджеру или уточнить вопрос.\n"
    )
    return f"{base}{no_context_instruction}"


async def _inject_rag_context_async(
    wiki_rag,
    user_content: str,
    base_prompt: str | None,
    rag_mode: str,
    collection_ids: list[int],
) -> str | None:
    """Async version of _inject_rag_context — includes vector search results."""
    if not wiki_rag or not user_content or rag_mode == "none" or not collection_ids:
        return base_prompt

    if not wiki_rag.vector_search_available:
        return await asyncio.to_thread(
            _inject_rag_context, wiki_rag, user_content, base_prompt, rag_mode, collection_ids
        )

    if len(collection_ids) == 1:
        wiki_context = await wiki_rag.retrieve_async(
            user_content, top_k=7, max_chars=4000, collection_id=collection_ids[0]
        )
    else:
        wiki_context = await wiki_rag.retrieve_multi_async(
            user_content, collection_ids, top_k=7, max_chars=4000
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

    no_context_instruction = (
        "\n\n--- ВАЖНО ---\n"
        "По данному запросу в базе знаний не найдено релевантной информации. "
        "НЕ выдумывай ответ. Если ты не уверен в точности информации — "
        "честно скажи, что не нашёл данных в базе знаний, и предложи "
        "обратиться к менеджеру или уточнить вопрос.\n"
    )
    return f"{base}{no_context_instruction}"


def _get_model_name(llm_service) -> str:
    """Extract model name from LLM service for token counting."""
    if hasattr(llm_service, "model_name") and llm_service.model_name:
        return llm_service.model_name
    if hasattr(llm_service, "config") and isinstance(llm_service.config, dict):
        return llm_service.config.get("model_name", "")
    return "claude"


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------


class ChatServiceImpl:
    """Facade implementing the ChatService Protocol.

    Wraps existing ``ChatService`` (CRUD) and ``ChatShareService`` singletons,
    adds LLM generation methods (``send_message``, ``stream_message``).

    Receives ``ServiceContainer`` for lazy access to LLM and RAG services
    which may change at runtime.
    """

    def __init__(self, container: ServiceContainer) -> None:
        self._container = container
        # Lazy import to avoid circular deps
        from modules.chat.service import chat_service, chat_share_service

        self._crud = chat_service
        self._share = chat_share_service

    # -- Sessions (delegate to CRUD) ------------------------------------------

    async def create_session(
        self,
        *,
        source: str = "admin",
        source_id: str | None = None,
        title: str | None = None,
        system_prompt: str | None = None,
        owner_id: int | None = None,
        workspace_id: int = 1,
    ) -> dict:
        return await self._crud.create_session(
            title=title,
            system_prompt=system_prompt,
            source=source,
            source_id=source_id,
            owner_id=owner_id,
            workspace_id=workspace_id,
        )

    async def get_session(self, session_id: str) -> dict | None:
        return await self._crud.get_session(session_id)

    async def list_sessions(
        self,
        *,
        owner_id: int | None = None,
        workspace_id: int | None = None,
    ) -> list[dict]:
        return await self._crud.list_sessions(owner_id=owner_id, workspace_id=workspace_id)

    async def delete_session(self, session_id: str) -> bool:
        return await self._crud.delete_session(session_id)

    # -- Messages (delegate to CRUD) ------------------------------------------

    async def get_history(self, session_id: str) -> list[dict]:
        return await self._crud.get_active_messages(session_id)

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        parent_id: str | None = None,
    ) -> dict | None:
        return await self._crud.add_message(session_id, role, content, parent_id=parent_id)

    # -- Generation (LLM) ----------------------------------------------------

    async def send_message(
        self,
        session_id: str,
        content: str,
        *,
        llm_service=None,
        session_data: dict | None = None,
        system_prompt: str | None = None,
        rag_mode: str = "all",
        collection_ids: list[int] | None = None,
        parent_id: str | None = None,
        extra_data: str | None = None,
    ) -> dict:
        """Send a user message, call LLM (non-streaming), save and return assistant reply.

        Args:
            session_id: Chat session ID.
            content: User message text (already includes OCR if any).
            llm_service: Resolved LLM service instance (CloudLLMService/VLLMLLMService).
            session_data: Pre-fetched session dict (avoids redundant DB call).
            system_prompt: Override system prompt (from widget/mobile/override).
            rag_mode: RAG mode ("all", "selected", "collection", "none").
            collection_ids: Knowledge collection IDs for RAG.
            parent_id: Parent message ID (for branching on edit/regenerate).
            extra_data: JSON string with image metadata etc.

        Returns:
            Saved assistant message dict.
        """
        llm = llm_service or self._container.llm_service
        if not llm:
            raise RuntimeError("LLM service not available")

        session = session_data or await self._crud.get_session(session_id)
        if not session:
            raise RuntimeError(f"Session {session_id} not found")

        wiki_rag = self._container.wiki_rag_service
        coll_ids = collection_ids or []
        use_agentic = _should_use_agentic_rag(llm, rag_mode, coll_ids, wiki_rag)
        use_web_search = bool(session.get("web_search_enabled")) and _supports_tools(llm)

        # Build prompt
        prompt = system_prompt or session.get("system_prompt")
        if not prompt:
            prompt = _load_platform_agent_prompt()
        if not prompt and hasattr(llm, "get_system_prompt"):
            prompt = llm.get_system_prompt()

        if not use_agentic:
            prompt = await _inject_rag_context_async(wiki_rag, content, prompt, rag_mode, coll_ids)

        prompt = _inject_context_files(prompt, session)

        messages = await self._crud.get_messages_for_llm(
            session_id,
            _finalize_prompt(prompt, agentic_rag=use_agentic, web_search=use_web_search),
        )

        # Trim context
        from app.utils.tokens import get_context_window, trim_messages

        model = _get_model_name(llm)
        context_window = get_context_window(model)
        messages, _ = trim_messages(messages, context_window)

        # Generate
        if use_agentic or use_web_search:
            tools = _build_tools(use_agentic, use_web_search)
            loop_messages = list(messages)
            response_text = ""

            for _iteration in range(MAX_TOOL_ITERATIONS):
                result = llm.generate_response_from_messages(
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
                    fn_name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    result_text, _ = _execute_tool_call(fn_name, args, wiki_rag, coll_ids)
                    loop_messages.append(
                        {"role": "tool", "tool_call_id": tc["id"], "content": result_text}
                    )
        else:
            response_text = llm.generate_response_from_messages(messages, stream=False)
            if hasattr(response_text, "__iter__") and not isinstance(response_text, str):
                response_text = "".join(response_text)

        assistant_msg = await self._crud.add_message(
            session_id, "assistant", response_text, parent_id=parent_id
        )
        return assistant_msg

    async def stream_message(
        self,
        session_id: str,
        content: str,
        *,
        llm_service=None,
        session_data: dict | None = None,
        user_msg: dict | None = None,
        system_prompt: str | None = None,
        rag_mode: str = "all",
        collection_ids: list[int] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Send a user message, stream the LLM response, save the result.

        Yields ``StreamChunk`` dicts that the router serialises to SSE events.
        The user message should already be saved before calling this method
        (``user_msg`` is the saved dict echoed back to the client).

        Args:
            session_id: Chat session ID.
            content: User message text (already includes OCR if any).
            llm_service: Resolved LLM service instance.
            session_data: Pre-fetched session dict.
            user_msg: Already-saved user message dict (echoed as first SSE event).
            system_prompt: Override system prompt.
            rag_mode: RAG mode.
            collection_ids: Knowledge collection IDs for RAG.

        Yields:
            StreamChunk dicts with ``type`` field for SSE serialization.
        """
        llm = llm_service or self._container.llm_service
        if not llm:
            yield StreamChunk(type="error", content="LLM service not available")
            return

        session = session_data or await self._crud.get_session(session_id)
        if not session:
            yield StreamChunk(type="error", content=f"Session {session_id} not found")
            return

        wiki_rag = self._container.wiki_rag_service
        coll_ids = collection_ids or []
        use_agentic = _should_use_agentic_rag(llm, rag_mode, coll_ids, wiki_rag)
        use_web_search = bool(session.get("web_search_enabled")) and _supports_tools(llm)

        # Build prompt
        prompt = system_prompt or session.get("system_prompt")
        if not prompt:
            prompt = _load_platform_agent_prompt()
        if not prompt and hasattr(llm, "get_system_prompt"):
            prompt = llm.get_system_prompt()

        if not use_agentic:
            prompt = await _inject_rag_context_async(wiki_rag, content, prompt, rag_mode, coll_ids)

        prompt = _inject_context_files(prompt, session)

        messages = await self._crud.get_messages_for_llm(
            session_id,
            _finalize_prompt(prompt, agentic_rag=use_agentic, web_search=use_web_search),
        )

        # Trim context
        from app.utils.tokens import count_message_tokens, get_context_window, trim_messages

        model = _get_model_name(llm)
        context_window = get_context_window(model)
        messages, was_trimmed = trim_messages(messages, context_window)
        if was_trimmed:
            logger.info(f"Trimmed context for session {session_id}")

        # Echo user message
        if user_msg:
            yield StreamChunk(type="user_message", message=user_msg)

        full_response: list[str] = []

        try:
            if use_agentic or use_web_search:
                # Agentic RAG loop
                tools = _build_tools(use_agentic, use_web_search)
                loop_messages = list(messages)

                for _iteration in range(MAX_TOOL_ITERATIONS):
                    content_chunks: list[str] = []
                    tool_calls_result = None

                    for event in llm.generate_response_from_messages(
                        loop_messages, stream=True, tools=tools
                    ):
                        if isinstance(event, dict):
                            if event["type"] == "content":
                                content_chunks.append(event["content"])
                                full_response.append(event["content"])
                                yield StreamChunk(type="chunk", content=event["content"])
                            elif event["type"] == "tool_calls":
                                tool_calls_result = event["tool_calls"]
                        else:
                            full_response.append(event)
                            yield StreamChunk(type="chunk", content=event)

                    if not tool_calls_result:
                        break

                    # Execute tool calls
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
                        try:
                            args = json.loads(tc["function"]["arguments"])
                        except json.JSONDecodeError:
                            args = {}
                        query = args.get("query", "")
                        yield StreamChunk(type="tool_start", name=fn_name, query=query)

                        result_text, found = _execute_tool_call(fn_name, args, wiki_rag, coll_ids)
                        yield StreamChunk(type="tool_end", name=fn_name, found=found)

                        loop_messages.append(
                            {"role": "tool", "tool_call_id": tc["id"], "content": result_text}
                        )
            else:
                # One-shot streaming
                for chunk in llm.generate_response_from_messages(messages, stream=True):
                    full_response.append(chunk)
                    yield StreamChunk(type="chunk", content=chunk)

            # Save full response
            response_text = "".join(full_response)
            assistant_msg = await self._crud.add_message(session_id, "assistant", response_text)

            # Token usage
            all_msgs = messages + [{"role": "assistant", "content": response_text}]
            tokens = count_message_tokens(all_msgs, model)
            percent = round(tokens / context_window * 100, 1) if context_window else 0
            token_usage = {
                "tokens": tokens,
                "context_window": context_window,
                "percent": percent,
                "trimmed": was_trimmed,
            }

            yield StreamChunk(
                type="assistant_message", message=assistant_msg, token_usage=token_usage
            )
            yield StreamChunk(type="done", done=True)

        except Exception as e:
            logger.error(f"Chat stream error: {e}")
            # Save partial response so the user doesn't lose what was already streamed
            partial_text = "".join(full_response).strip()
            if partial_text:
                try:
                    partial_msg = await self._crud.add_message(
                        session_id, "assistant", partial_text
                    )
                    logger.info(
                        f"Saved partial response ({len(partial_text)} chars) for session {session_id}"
                    )
                    yield StreamChunk(
                        type="assistant_message", message=partial_msg, token_usage=None
                    )
                except Exception as save_err:
                    logger.error(f"Failed to save partial response: {save_err}")
            yield StreamChunk(type="error", content=str(e))

    # -- Sharing (delegate to ChatShareService) -------------------------------

    async def share_session(
        self,
        session_id: str,
        user_id: int,
        *,
        permission: str = "read",
        shared_by: int | None = None,
        branch_message_id: str | None = None,
    ) -> ShareInfo:
        result = await self._share.add_share(
            session_id, user_id, permission, shared_by, branch_message_id
        )
        return ShareInfo(
            id=result.get("id", 0),
            session_id=result.get("session_id", session_id),
            user_id=result.get("user_id", user_id),
            permission=result.get("permission", permission),
            shared_by=result.get("shared_by"),
            shared_at=result.get("shared_at"),
        )

    async def unshare_session(
        self,
        session_id: str,
        user_id: int,
    ) -> bool:
        return await self._share.remove_share(session_id, user_id)


# Module-level singleton — NOT created here because it needs ServiceContainer.
# Created in startup and set via: chat_service_facade = ChatServiceImpl(container)
chat_service_facade: Optional[ChatServiceImpl] = None
