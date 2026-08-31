"""Turn a conversation into a catalog search query.

The offer search used to run on the raw text of the latest message. That works
for a first request and breaks on every follow-up, because a follow-up is a
*refinement*, not a request. Real case (01.09.2026):

    — Контактор модульный NCH8-20/20 … есть в наличии?
    — ✅ есть, 5 432 ₸
    — модульный не подходит, нам нужен промышленный тип
    — «промышленных силовых контакторов не нашёл, в каталоге только модульные»

Searching that last line put «модульный» — the word the client used to say what
he did NOT want — at the top of the query, so the search returned exactly the
modular contactors he had just rejected, and the assistant honestly reported
what it was handed. Meanwhile the catalog held 556 power contactors.

One cheap LLM call reads the last few turns and returns what to search for and
what the client has ruled out. Any failure falls back to the raw message, i.e.
to the previous behaviour — this must never break a chat.
"""

import asyncio
import json
import logging
import re
from typing import Optional


logger = logging.getLogger(__name__)

# Enough to carry the subject and one or two refinements; keeps the call cheap.
MAX_TURNS = 6
MAX_CHARS_PER_TURN = 400
MAX_EXCLUDE = 5

_SYSTEM = """Ты — нормализатор поисковых запросов для каталога электротехники.
По переписке определи, какой товар клиент ищет ПРЯМО СЕЙЧАС.

Верни СТРОГО JSON, без markdown и пояснений:
{"query": "<товарный запрос>", "exclude": ["<что клиент отверг>"]}

Правила:
- query — предмет + ключевые характеристики, с учётом всей переписки.
  Если клиент уточняет предыдущий запрос, предмет берётся оттуда.
- Пиши словами каталога: «контактор силовой», а не «нужен промышленный тип».
- В query не должно быть слов, которые клиент отверг, и слов-обращений.
- exclude — признаки, от которых клиент явно отказался.
  «модульный не подходит» → ["модульный"]. Если таких нет — пустой список.
- Только JSON, ничего больше."""

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _extract_json(raw: str) -> Optional[dict]:
    """Parse the model's answer, tolerating ```json fences and stray prose."""
    text = _FENCE_RE.sub("", (raw or "").strip()).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _build_messages(history: list[dict], content: str) -> list[dict]:
    turns = [
        m
        for m in (history or [])
        if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()
    ]
    # The current message may or may not already be persisted in history.
    if turns and turns[-1].get("role") == "user" and turns[-1].get("content") == content:
        turns = turns[:-1]
    turns = turns[-MAX_TURNS:]

    lines = [
        f"{'Клиент' if m['role'] == 'user' else 'Ассистент'}: {m['content'][:MAX_CHARS_PER_TURN]}"
        for m in turns
    ]
    lines.append(f"Клиент: {content[:MAX_CHARS_PER_TURN]}")
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": "\n".join(lines)},
    ]


async def build_search_query(llm, history: list[dict], content: str) -> tuple[str, list[str]]:
    """Return (query, exclude) for the offer search.

    Falls back to ``(content, [])`` — the previous behaviour — whenever there is
    no history to reason about, the LLM is unavailable, or the answer is not
    usable JSON.
    """
    if not content or not llm:
        return content, []
    # First message of a session: the raw text IS the request, no call needed.
    prior_users = [
        m
        for m in (history or [])
        if m.get("role") == "user" and (m.get("content") or "") != content
    ]
    if not prior_users:
        return content, []

    try:
        messages = _build_messages(history, content)
        raw = await asyncio.to_thread(
            llm.generate_response_from_messages,
            messages,
            stream=False,
        )
        if not isinstance(raw, str):
            raw = (raw or {}).get("content", "") if isinstance(raw, dict) else ""
        data = _extract_json(raw)
        if not data:
            logger.warning("query_builder: unusable answer, falling back to raw message")
            return content, []

        query = (data.get("query") or "").strip()
        exclude_raw = data.get("exclude")
        exclude = [
            str(x).strip()
            for x in (exclude_raw if isinstance(exclude_raw, list) else [])
            if str(x).strip()
        ][:MAX_EXCLUDE]
        if not query:
            return content, exclude
        logger.info("query_builder: %r -> %r exclude=%s", content[:60], query[:60], exclude)
        return query, exclude
    except Exception as e:  # never break the chat over query rewriting
        logger.warning("query_builder failed (%s), using raw message", e)
        return content, []
