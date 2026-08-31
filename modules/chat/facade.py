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

# Sessions attached to one of these knowledge collections get unified product
# offer injection (procurement code-pipeline). Opt-in so other tenants are
# unaffected. Default: the WooCommerce catalog collection (id 6).
_PROCUREMENT_CATALOG_COLLECTIONS = {
    int(x)
    for x in os.getenv("PROCUREMENT_CATALOG_COLLECTIONS", "6").split(",")
    if x.strip().isdigit()
}


def _is_procurement_session(collection_ids: list[int]) -> bool:
    """True if the session is attached to a procurement catalog collection."""
    return bool(collection_ids) and bool(
        _PROCUREMENT_CATALOG_COLLECTIONS.intersection(collection_ids)
    )


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


async def _resolve_session_persona(session: dict, persona_id: str | None):
    """Resolve the persona backing a session.

    An explicit ``persona_id`` (channel instance the message came through)
    wins over the one stored on the session itself. Returns None when nothing
    is attached — existing chats keep their current behaviour.
    """
    from modules.llm.persona import resolve_persona

    persona = await resolve_persona(persona_id)
    if persona:
        return persona
    return await resolve_persona(session.get("llm_persona"))


def _build_prompt(
    explicit: str | None,
    session: dict,
    persona,
    llm,
) -> str | None:
    """System prompt precedence: explicit → session → persona → platform agent → service.

    The persona sits below the session's own prompt so a per-chat override
    always wins, and above ``platform-agent.md`` so attaching a persona
    actually changes the assistant.
    """
    prompt = explicit or session.get("system_prompt")
    if not prompt and persona:
        prompt = persona.system_prompt
    if not prompt:
        prompt = _load_platform_agent_prompt()
    if not prompt and hasattr(llm, "get_system_prompt"):
        prompt = llm.get_system_prompt()
    return prompt


def _llm_accepts_params(llm) -> bool:
    """True if the LLM service takes per-call generation params.

    Guards against provider classes that predate the persona feature.
    """
    import inspect

    try:
        sig = inspect.signature(llm.generate_response_from_messages)
    except (TypeError, ValueError):
        return False
    return "params" in sig.parameters


def _generate(llm, messages, *, stream: bool, tools=None, params=None):
    """Call the LLM, passing per-call params only when supported."""
    kwargs: dict = {"stream": stream}
    if tools:
        kwargs["tools"] = tools
    if params and _llm_accepts_params(llm):
        kwargs["params"] = params
    return llm.generate_response_from_messages(messages, **kwargs)


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


def _supports_web_search(llm_service) -> bool:
    """Web search needs tool calling — native or emulated by the endpoint.

    The Claude bridge has no native function calling but emulates it in the
    prompt, so web search works there even though agentic RAG stays off.
    """
    if _supports_tools(llm_service):
        return True
    if getattr(llm_service, "supports_tools_emulated", False):
        return True
    return hasattr(llm_service, "provider") and getattr(
        llm_service.provider, "supports_tools_emulated", False
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


async def _inject_offer_context(
    prompt: str | None,
    content: str,
    session: dict,
    collection_ids: list[int],
    *,
    llm=None,
    history: list[dict] | None = None,
) -> str | None:
    """Inject real product offers (unified search) for procurement sessions.

    Opt-in: only when the session is attached to a catalog collection
    (``_PROCUREMENT_CATALOG_COLLECTIONS``). Deterministic search returns only
    real rows — never invented. Dealer (supplier) prices are gated to internal
    contexts (``source == 'admin'``); client channels (widget/telegram/mobile)
    see own-site retail offers only. Best-effort: never breaks the chat.
    """
    if not content or not collection_ids:
        return prompt
    if not _PROCUREMENT_CATALOG_COLLECTIONS.intersection(collection_ids):
        return prompt
    try:
        from modules.procurement.service import offer_service

        manager_ctx = session.get("source") == "admin"
        # A follow-up («модульный не подходит, нужен промышленный») is a
        # refinement, not a request: searching its raw text returned exactly the
        # positions the client had just rejected. Build the query from the
        # dialogue instead; falls back to `content` when there is no history.
        from modules.procurement.query_builder import build_search_query

        search_query, exclude = await build_search_query(llm, history or [], content)
        # Exact keyword search for offers (prices/stock/articles — КП-exact rule).
        offers = await offer_service.search(search_query, limit=8, exclude=exclude)

        # Supplementary meaning-based context from the catalog collection (rich
        # descriptions) — helps vague/functional queries («чем питать насос»).
        # Prices/stock/articles still come ONLY from the exact offers above.
        semantic_ctx = ""
        try:
            from app.dependencies import get_container

            wiki = get_container().wiki_rag_service
            cat_ids = list(_PROCUREMENT_CATALOG_COLLECTIONS.intersection(collection_ids))
            if wiki and cat_ids:
                ctx = await wiki.retrieve_async(
                    search_query, top_k=3, max_chars=1200, collection_id=cat_ids[0]
                )
                semantic_ctx = (ctx or "").strip()
        except Exception as e:
            logger.warning("catalog semantic context failed: %s", e)

        if not manager_ctx:
            offers = [o for o in offers if o.get("source") == "site"]
        if not offers:
            block = (
                "\n\n--- ПОИСК ПО БАЗЕ ---\n"
                "По этому запросу точных позиций в базе (каталог сайта"
                + (" + прайсы поставщиков" if manager_ctx else "")
                + ") не найдено. НЕ выдумывай цену/артикул. Уточни параметры "
                "(производитель, номинал, характеристику) и предложи передать "
                "запрос менеджеру для подбора у поставщиков."
            )
            # Managers get routing: which supplier(s) to request from.
            if manager_ctx:
                from modules.procurement.routing import route

                r = route(search_query)
                if r["suppliers"]:
                    names = ", ".join(
                        f"{s['name']} (тип {s['type']})"
                        + (" ⚠️конкурент, не раскрывать объект/клиента" if s["competitor"] else "")
                        for s in r["suppliers"]
                    )
                    cat = f"«{r['category']}»" if r["category"] else "по профилю"
                    block += (
                        f"\nМАРШРУТ ({cat}"
                        + (", клиент из Атырау → ЭКТ первым" if r["atyrau_priority"] else "")
                        + f"): запросить в порядке — {names}."
                    )
            if semantic_ctx:
                block += (
                    "\n\n--- СПРАВОЧНО ИЗ КАТАЛОГА (описания; точные цены/наличие "
                    "уточнит менеджер) ---\n" + semantic_ctx[:1200]
                )
            return (prompt or "") + block

        # For managers, compute purchase + client (КП) prices for supplier
        # offers. Rate fetched once (cached per day).
        rate_info = None
        if manager_ctx and any(o.get("source") == "supplier" for o in offers):
            from modules.procurement.rate_service import get_usd_kzt

            rate_info = await get_usd_kzt()

        lines = []
        for o in offers:
            # price=0 — это «цены нет в базе» (#841), а не бесплатный товар:
            # печатать «0 KZT» значит подсказать ассистенту назвать нулевую цену
            price = f"{o['price']:g} {o['currency']}" if o.get("price") else "цена не указана"
            if o.get("in_stock") is True:
                stock = "в наличии"
            elif o.get("in_stock") is False:
                stock = "под заказ"
            else:
                stock = ""
            art = f"арт. {o['article']}" if o.get("article") else ""
            src = ""
            if manager_ctx and o.get("source") == "supplier":
                from modules.procurement.pricing import price_offer

                p = await price_offer(o, rate_info=rate_info)
                supplier_lbl = o.get("supplier_name") or ""
                if p.get("ok"):
                    flag = " ⚠️НУЛЕВАЯ МАРЖА→директору" if p.get("zero_margin_flag") else ""
                    src = (
                        f" · {supplier_lbl}: закуп {p['purchase_price']:.0f}₸ →"
                        f" клиенту {p['client_price']:.0f}₸{flag}"
                    )
                else:
                    src = f" · {supplier_lbl} (закупочная)"
            parts = [o.get("name") or "", art, price, stock]
            lines.append("- " + " | ".join(p for p in parts if p) + src)

        block = (
            "\n\n--- РЕАЛЬНЫЕ ПОЗИЦИИ ИЗ БАЗЫ (только эти данные для цен, наличия, артикулов) ---\n"
            + "\n".join(lines)
            + "\n\nЕсли нужной позиции здесь нет — честно скажи «не нашёл», не выдумывай цену/артикул."
        )
        if manager_ctx:
            block += (
                " «клиенту» — цена для КП (наценка+НДС уже учтены); «закуп» — закупочная, "
                "конфиденциальна, клиенту не называть. Позиции с ⚠️НУЛЕВОЙ МАРЖОЙ не ставить в "
                "КП автоматически — показать директору."
            )
            if rate_info and rate_info.get("rate"):
                stale = " (fallback, подтвердить у директора)" if rate_info.get("stale") else ""
                block += (
                    f" Курс USD/KZT {rate_info['rate']} на {rate_info.get('date')}"
                    f" ({rate_info.get('source')}){stale} — указывать в КП."
                )
            block += (
                " Если просят КП/счёт — таблица (№|Наименование|Артикул|Кол-во|Цена клиенту|Сумма) "
                "по ценам «клиенту», итог с разбивкой НДС 16%, строка про доставку по факту веса/"
                "габаритов и срок действия цен. Поставщиков клиенту НЕ раскрывать; свет Мегазаказа — "
                "как бренд Stalker Electric. Это ЧЕРНОВИК на подтверждение директора."
            )
        if semantic_ctx:
            block += (
                "\n\n--- СПРАВОЧНО ИЗ КАТАЛОГА (описания/характеристики для понимания; "
                "цены, наличие и артикулы бери ТОЛЬКО из позиций выше) ---\n" + semantic_ctx[:1200]
            )
        return (prompt or "") + block
    except Exception as e:
        logger.warning("offer injection failed: %s", e)
        return prompt


def _get_model_name(llm_service) -> str:
    """Extract model name from LLM service for token counting."""
    if hasattr(llm_service, "model_name") and llm_service.model_name:
        return llm_service.model_name
    if hasattr(llm_service, "config") and isinstance(llm_service.config, dict):
        return llm_service.config.get("model_name", "")
    return "claude"


def _get_context_window(llm_service) -> int:
    """Размер контекста модели.

    Локальный vLLM сообщает реальный max_model_len (например 4096) — эвристика
    по имени модели его не знает и вернула бы 128k, из-за чего запрос уходил бы
    в vLLM без обрезки и получал 400 "maximum context length".
    """
    from app.utils.tokens import get_context_window

    reported = getattr(llm_service, "max_model_len", None)
    if isinstance(reported, int) and reported > 0:
        return reported
    return get_context_window(_get_model_name(llm_service))


def _is_claude_provider(llm_service) -> bool:
    """True if llm_service is a Claude provider (claude / claude_bridge)."""
    ptype = getattr(llm_service, "provider_type", None)
    if ptype in ("claude", "claude_bridge"):
        return True
    cfg = getattr(llm_service, "config", None)
    return isinstance(cfg, dict) and cfg.get("provider_type") in ("claude", "claude_bridge")


async def _log_llm_usage(
    llm_service,
    *,
    user_id: int | None,
    source: str | None,
    source_id: str | None,
    action: str = "chat",
) -> None:
    """Persist last_usage from llm_service to UsageLog. Best-effort, never raises."""
    try:
        usage = getattr(llm_service, "last_usage", None)
        if not usage or not _is_claude_provider(llm_service):
            return
        total = int(usage.get("total_tokens") or 0)
        if total <= 0:
            return
        from db.database import AsyncSessionLocal
        from db.repositories.usage import UsageRepository

        async with AsyncSessionLocal() as session:
            repo = UsageRepository(session)
            await repo.log_usage(
                service_type="llm",
                action=action,
                units_consumed=total,
                source=source,
                source_id=source_id,
                user_id=user_id,
                details={
                    "input_tokens": int(usage.get("input_tokens") or 0),
                    "output_tokens": int(usage.get("output_tokens") or 0),
                    "model": usage.get("model"),
                    "estimated": bool(usage.get("estimated")),
                },
            )
            await session.commit()
    except Exception as e:  # pragma: no cover — never break chat on logging failure
        logger.debug(f"_log_llm_usage failed: {e}")


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
        persona_id: str | None = None,
        gen_params: dict | None = None,
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
            persona_id: Persona (LLM preset) from the channel instance; falls
                back to the one stored on the session.
            gen_params: Explicit generation parameters overriding the persona's.
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
        use_web_search = bool(session.get("web_search_enabled")) and _supports_web_search(llm)

        # Build prompt + generation params from the attached persona
        from modules.llm.persona import merge_params

        persona = await _resolve_session_persona(session, persona_id)
        prompt = _build_prompt(system_prompt, session, persona, llm)
        params = merge_params(gen_params, persona)

        if not use_agentic:
            if _is_procurement_session(coll_ids):
                # Procurement sessions use structured offer search (real prices/
                # stock across site + suppliers) instead of wiki-RAG injection.
                prompt = await _inject_offer_context(
                    prompt,
                    content,
                    session,
                    coll_ids,
                    llm=llm,
                    history=await self._crud.get_messages_for_llm(session_id),
                )
            else:
                prompt = await _inject_rag_context_async(
                    wiki_rag, content, prompt, rag_mode, coll_ids
                )

        prompt = _inject_context_files(prompt, session)

        messages = await self._crud.get_messages_for_llm(
            session_id,
            _finalize_prompt(prompt, agentic_rag=use_agentic, web_search=use_web_search),
        )

        # Trim context
        from app.utils.tokens import trim_messages

        context_window = _get_context_window(llm)
        messages, _ = trim_messages(messages, context_window)

        # Generate
        if use_agentic or use_web_search:
            tools = _build_tools(use_agentic, use_web_search)
            loop_messages = list(messages)
            response_text = ""

            for _iteration in range(MAX_TOOL_ITERATIONS):
                result = _generate(llm, loop_messages, stream=False, tools=tools, params=params)
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
            response_text = _generate(llm, messages, stream=False, params=params)
            if hasattr(response_text, "__iter__") and not isinstance(response_text, str):
                response_text = "".join(response_text)

        assistant_msg = await self._crud.add_message(
            session_id, "assistant", response_text, parent_id=parent_id
        )
        await _log_llm_usage(
            llm,
            user_id=session.get("owner_id"),
            source=session.get("source") or "admin",
            source_id=session_id,
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
        persona_id: str | None = None,
        gen_params: dict | None = None,
        rag_mode: str = "all",
        collection_ids: list[int] | None = None,
        web_search: bool | None = None,
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
        # web_search override lets non-session callers (widget) enable it from
        # their own config; otherwise fall back to the session flag.
        want_web_search = (
            web_search if web_search is not None else bool(session.get("web_search_enabled"))
        )
        use_web_search = want_web_search and _supports_web_search(llm)

        # Build prompt + generation params from the attached persona
        from modules.llm.persona import merge_params

        persona = await _resolve_session_persona(session, persona_id)
        prompt = _build_prompt(system_prompt, session, persona, llm)
        params = merge_params(gen_params, persona)

        if not use_agentic:
            if _is_procurement_session(coll_ids):
                # Procurement sessions use structured offer search (real prices/
                # stock across site + suppliers) instead of wiki-RAG injection.
                prompt = await _inject_offer_context(
                    prompt,
                    content,
                    session,
                    coll_ids,
                    llm=llm,
                    history=await self._crud.get_messages_for_llm(session_id),
                )
            else:
                prompt = await _inject_rag_context_async(
                    wiki_rag, content, prompt, rag_mode, coll_ids
                )

        prompt = _inject_context_files(prompt, session)

        messages = await self._crud.get_messages_for_llm(
            session_id,
            _finalize_prompt(prompt, agentic_rag=use_agentic, web_search=use_web_search),
        )

        # Trim context
        from app.utils.tokens import count_message_tokens, trim_messages

        model = _get_model_name(llm)
        context_window = _get_context_window(llm)
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

                    for event in _generate(
                        llm, loop_messages, stream=True, tools=tools, params=params
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
                for chunk in _generate(llm, messages, stream=True, params=params):
                    full_response.append(chunk)
                    yield StreamChunk(type="chunk", content=chunk)

            # Save full response
            response_text = "".join(full_response)
            assistant_msg = await self._crud.add_message(session_id, "assistant", response_text)

            # Per-user LLM token accounting (Claude only — see _is_claude_provider)
            await _log_llm_usage(
                llm,
                user_id=session.get("owner_id"),
                source=session.get("source") or "admin",
                source_id=session_id,
            )

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
