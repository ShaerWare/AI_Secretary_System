"""From a client dialogue to КП positions.

The assistant drafts a КП when the client asks for one («пришлите КП», «выставьте
счёт»). One LLM call reads the dialogue and lists what the client wants and how
many; every position is then matched against the real catalog by the same
deterministic search the chat uses. A position that does not match confidently
or has no price is NOT put into the document — it goes to ``flags`` for the
manager. The PIM asks the same of an AI agent: never invent goods or prices.
"""

import asyncio
import json
import logging
import math
import re
from typing import Any, Optional


logger = logging.getLogger(__name__)

KP_REQUEST_RE = re.compile(
    r"\bкп\b|коммерческ\w*\s+предлож|\bсч[её]т\w*\s+на\s+оплат|выстав\w*\s+сч[её]т"
    r"|\bсч[её]т\s+(?:на|по)\b|просчит|расч[её]т\w*\s+(?:стоимост|цен)|\bсмет",
    re.IGNORECASE,
)

MAX_TURNS = 12
MAX_CHARS_PER_TURN = 1500
MAX_ITEMS = 50
MAX_SUMMARY_CHARS = 600

_SYSTEM = """Ты извлекаешь из переписки с клиентом позиции для коммерческого предложения
(электротехника, Казахстан).

Верни СТРОГО JSON без markdown и пояснений:
{"customer": {"name": "", "contact": "", "bin": "", "email": ""},
 "items": [{"query": "<товар как его назвал клиент: тип, номинал, серия, артикул>", "qty": 1}],
 "request_number": "",
 "summary": ""}

Правила:
- items — только то, что КЛИЕНТ хочет получить в КП. Позиции, которые клиент
  отверг или заменил, не включай. Варианты, которые лишь предлагал ассистент,
  включай, только если клиент их выбрал.
- query пиши словами каталога, с артикулом, если клиент его назвал.
- qty — число из слов клиента (штуки, метры). Не указано — 1.
- customer.name — организация клиента (ТОО/ИП), если он её назвал; иначе пусто.
  bin — БИН/ИИН, если назван. Ничего не выдумывай.
- request_number — номер заявки клиента, если назван.
- summary — 1–2 предложения для менеджера: что клиенту нужно и для чего
  (объект, задача, сроки, если он их назвал). Без цен и без того, что
  предлагал ассистент. Ничего не выдумывай.
- Только JSON."""

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def is_kp_request(text: str) -> bool:
    return bool(KP_REQUEST_RE.search(text or ""))


def _parse_json(raw: str) -> Optional[dict]:
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


def _dialogue(messages: list[dict]) -> str:
    turns = [
        m
        for m in messages or []
        if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()
    ][-MAX_TURNS:]
    return "\n".join(
        f"{'Клиент' if m['role'] == 'user' else 'Ассистент'}: {m['content'][:MAX_CHARS_PER_TURN]}"
        for m in turns
    )


def _qty(value: Any) -> int:
    """PIM counts are integers; a fractional quantity (metres) is rounded up."""
    try:
        q = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return 1
    return max(1, math.ceil(q)) if q > 0 else 1


async def extract_request(llm, messages: list[dict]) -> Optional[dict]:
    """LLM pass over the dialogue. None when the model gave nothing usable."""
    text = _dialogue(messages)
    if not text or not llm:
        return None
    prompt = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": text},
    ]
    try:
        raw = await asyncio.to_thread(llm.generate_response_from_messages, prompt, stream=False)
    except Exception as e:
        logger.warning("kp extract: LLM call failed: %s", e)
        return None
    if not isinstance(raw, str):
        raw = (raw or {}).get("content", "") if isinstance(raw, dict) else ""
    data = _parse_json(raw)
    if not data:
        logger.warning("kp extract: unusable LLM answer")
        return None
    items = []
    for it in (data.get("items") or [])[:MAX_ITEMS]:
        if not isinstance(it, dict):
            continue
        query = str(it.get("query") or "").strip()
        if query:
            items.append({"query": query, "qty": _qty(it.get("qty"))})
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    return {
        "items": items,
        "customer": {
            k: str(customer.get(k) or "").strip() for k in ("name", "contact", "bin", "email")
        },
        "request_number": str(data.get("request_number") or "").strip(),
        "summary": str(data.get("summary") or "").strip()[:MAX_SUMMARY_CHARS],
    }


def delivery_label(offer: dict) -> str:
    """Column «Срок поставки» of the PIM document. Says only what is known."""
    if offer.get("in_stock"):
        return "В наличии"
    days = offer.get("lead_time_days")
    if days:
        return f"{int(days)} дн."
    return "Срок уточняется"


async def resolve_items(requests: list[dict]) -> tuple[list[dict], list[str]]:
    """[{query, qty}] → priced PIM items + flags for what could not be quoted."""
    from modules.procurement.pricing import price_offer
    from modules.procurement.rate_service import get_usd_kzt
    from modules.procurement.service import offer_service

    rate_info = await get_usd_kzt()
    items: list[dict] = []
    flags: list[str] = []
    for req in requests:
        query, qty = req["query"], req["qty"]
        matches = await offer_service.search(query, limit=1, with_supply=False)
        if not matches or not matches[0].get("confident"):
            flags.append(
                f"«{query}» × {qty}: точного совпадения в каталоге нет — подобрать вручную"
            )
            continue
        offer = matches[0]
        if offer["source"] == "supplier":
            pricing = await price_offer(offer, rate_info=rate_info)
            if not pricing.get("ok"):
                flags.append(f"«{offer['name']}»: нет расчёта цены — уточнить у поставщика")
                continue
            if pricing.get("zero_margin_flag"):
                flags.append(f"«{offer['name']}»: закупка ≥ цены продажи — согласовать наценку")
                continue
            price = pricing["client_price"]
        else:
            price = offer.get("price") or 0
        if not price or price <= 0:
            flags.append(f"«{offer['name']}»: в каталоге нет цены — уточнить")
            continue
        items.append(
            {
                "sku": offer.get("article") or "",
                "name": offer.get("name") or query,
                "price": round(float(price), 2),
                "count": qty,
                "delivery": delivery_label(offer),
                "query": query,
            }
        )
    return items, flags
