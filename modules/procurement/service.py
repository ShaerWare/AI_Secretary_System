"""Procurement service: upsert offers per source + unified deterministic search.

This is the code-pipeline core of the "single search" feature. Adapters
(site / EKF / supplier) upsert real rows here; `search()` ranks them. The LLM
never invents data — it only reformulates rows this search returns.
"""

import json
import logging
import math
import re
from typing import List, Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy import select as sa_select

from db.database import AsyncSessionLocal
from db.retry import retry_on_busy
from modules.procurement.models import ProductOffer


logger = logging.getLogger(__name__)

# Ranking preference between sources when the same position appears in several.
# Own stock first, then EKF (direct API), then generic supplier price lists.
SOURCE_PRIORITY = {"site": 0, "ekf": 1, "supplier": 2}

_TOKEN_RE = re.compile(r"[^\w]+", re.UNICODE)

# Conversational filler dropped from queries so it doesn't match everything
# (e.g. "и" is a substring of most Russian words). Real product tokens stay.
_STOPWORDS = {
    "и",
    "в",
    "на",
    "с",
    "по",
    "для",
    "или",
    "что",
    "это",
    "есть",
    "нет",
    "нужен",
    "нужна",
    "нужно",
    "нужны",
    "надо",
    "хочу",
    "дай",
    "дайте",
    "какой",
    "какая",
    "какие",
    "почём",
    "почем",
    "цена",
    "цены",
    "сколько",
    "стоит",
    "стоят",
    "а",
    "у",
    "от",
    "до",
    "к",
    "же",
    "ли",
    "бы",
    "мне",
    "подбери",
    "подберите",
    "покажи",
    "найди",
    "ищу",
    "the",
    "and",
    "for",
    # request meta-words (email subjects), not product terms
    "запрос",
    "запроса",
    "стоимость",
    "стоимости",
    "цену",
    "прайс",
    "коммерческое",
    "кп",
    "счёт",
    "счет",
    "купить",
    "заказать",
    "заявка",
    "поставка",
    "поставку",
    "сообщение",
    "форма",
    "формы",
    # "из наличия", "помоги найти", "подобрать" — способ спросить, не товар
    "из",
    "наличия",
    "наличие",
    "помоги",
    "помогите",
    "найти",
    "подобрать",
    "подскажи",
    "подскажите",
    # единицы мощности: числовой номинал мы всё равно не сопоставляем, а как
    # токен «квт» цепляется к «2,2кВт» у колодок и удлинителей
    "квт",
    "вт",
    "ква",
}


def _norm(s: Optional[str]) -> str:
    """Lowercase + strip punctuation/space, Unicode-aware (handles Cyrillic)."""
    if not s:
        return ""
    return _TOKEN_RE.sub("", s.lower())


def _tokens(s: str) -> List[str]:
    return [t for t in _TOKEN_RE.split(s.lower()) if t]


# Colloquial / abbreviation → catalog wording (catalog names are formal, e.g.
# "преобразователь частоты", not "ЧРП"/"частотник"). Stemming handles inflected
# forms; this map covers abbreviations that share no stem with the full term.
_SYNONYMS = {
    "чрп": ["преобразователь", "частоты"],
    "пч": ["преобразователь", "частоты"],
    "частотник": ["преобразователь", "частоты"],
    "частотники": ["преобразователь", "частоты"],
    "частотный": ["преобразователь", "частоты"],
    "упп": ["устройство", "плавного", "пуска"],
    "узо": ["устройство", "защитного", "отключения"],
    "дифавтомат": ["дифференциальный", "автоматический"],
    "автоматы": ["автоматический", "выключатель"],
    # каталог не знает слова «промышленный»: модульные лежат в категории
    # «Модульное оборудование», силовые — в «Силовое оборудование»
    "промышленный": ["силовое"],
    "промышленные": ["силовое"],
    "промышленных": ["силовое"],
    "силовой": ["силовое"],
    "силовые": ["силовое"],
}

_STEM_LEN = 6


def _stem(t: str) -> str:
    """Crude Russian stemming: keep a prefix long enough to survive inflection
    but short enough to still match other forms (частоты → частот,
    контактор → контакт, электродвигатель → электродвигат).

    A flat 6-char prefix was too aggressive on long words: «электродвигатель»
    became «электр» and matched every «Электроустановочное изделие» in the
    catalog, so a query for a motor contactor came back full of socket blocks.
    Russian endings are 1–3 chars, so keeping ~70% of a long word is safe.
    """
    if len(t) <= _STEM_LEN:
        return t
    return t[: max(_STEM_LEN, math.ceil(len(t) * 0.7))]


# Номинальный ток: «18А», «120A» (кириллица и латиница), но не «NC1-1810»
# и не «220В». Первое вхождение — это и есть номинал позиции.
_AMP_RE = re.compile(r"(\d+)\s*[аa](?![\wа-яё])", re.UNICODE)


def _amperage(text: str) -> Optional[int]:
    """Номинальный ток из строки, если он там назван."""
    m = _AMP_RE.search((text or "").lower())
    return int(m.group(1)) if m else None


def _amp_bucket(q_amp: Optional[int], row_amp: Optional[int]) -> int:
    """Насколько номинал позиции далёк от запрошенного (0 — подходит).

    Без этого ранжирование не отличало 20 А от 120 А: на запрос «контактор
    20А 2НО» позиции на 120–225 А обгоняли 25-амперные только потому, что у
    них совпал второстепенный признак «2НО». Для электротехники номинал —
    определяющая характеристика, поэтому он стоит в ключе выше числа
    совпавших слов. Когда ток не назван (в запросе или в позиции) —
    измерение нейтрально и ничего не меняет.
    """
    if not q_amp:
        return 0
    if not row_amp:
        # Ток спросили, но в названии его нет («Контактор вакуумный NC9-630»).
        # Не выдаём это за совпадение: ниже подходящих, но выше явно чужих.
        return 2
    ratio = max(q_amp, row_amp) / min(q_amp, row_amp)
    if ratio <= 1.35:  # 18–25 А по запросу «20 А» — то, что нужно
        return 0
    return 1 if ratio <= 2.5 else 3


# «Катушка управления ДЛЯ КОНТАКТОРА NXC-18» — товар для товара, а не он сам.
_FOR_RE = re.compile(r"для\s+([\w-]+)", re.UNICODE)


def _is_accessory_for_query(name_low: str, first_stem: str, q_stems: set) -> bool:
    """True when the row is an accessory FOR something asked for, not the thing.

    Guard: if the row's own leading word is in the query, the client is asking
    for the accessory itself («катушка для контактора» → coils are the target),
    so it is not demoted.
    """
    if not q_stems or first_stem in q_stems:
        return False
    return any(any(m.group(1).startswith(s) for s in q_stems) for m in _FOR_RE.finditer(name_low))


def _expand_query_tokens(query: str) -> List[str]:
    """Tokenize + drop stopwords/short + expand abbreviations (dedup, ordered)."""
    out: List[str] = []
    for t in _tokens(query):
        if len(t) < 2 or t in _STOPWORDS:
            continue
        out.append(t)
        out.extend(_SYNONYMS.get(t, []))
    return list(dict.fromkeys(out))


class OfferService:
    """CRUD + search over `product_offers`."""

    @retry_on_busy()
    async def replace_source_offers(
        self,
        source: str,
        offers: List[dict],
        workspace_id: int = 1,
        scope_key: Optional[str] = None,
    ) -> int:
        """Full re-sync of one source: delete its offers, insert the fresh set.

        `offers` is a list of dicts with keys matching ProductOffer fields
        (must include source_key + name). When `scope_key` is given, only rows
        whose ``source_key`` starts with ``{scope_key}#`` are replaced — so
        several suppliers can share source='supplier' without wiping each other,
        and renaming a supplier doesn't orphan its rows. Returns rows written.
        """
        async with AsyncSessionLocal() as session:
            del_stmt = sa_delete(ProductOffer).where(
                ProductOffer.source == source,
                ProductOffer.workspace_id == workspace_id,
            )
            if scope_key is not None:
                del_stmt = del_stmt.where(ProductOffer.source_key.like(f"{scope_key}#%"))
            await session.execute(del_stmt)
            rows = 0
            for o in offers:
                if not o.get("source_key") or not o.get("name"):
                    continue
                extra = o.get("extra")
                session.add(
                    ProductOffer(
                        source=source,
                        source_key=str(o["source_key"]),
                        supplier_name=o.get("supplier_name"),
                        article=o.get("article"),
                        name=o["name"][:500],
                        brand=o.get("brand"),
                        category=o.get("category"),
                        price=o.get("price"),
                        currency=o.get("currency", "KZT"),
                        in_stock=o.get("in_stock"),
                        stock_qty=o.get("stock_qty"),
                        lead_time_days=o.get("lead_time_days"),
                        url=o.get("url"),
                        extra=json.dumps(extra, ensure_ascii=False) if extra else None,
                        workspace_id=workspace_id,
                    )
                )
                rows += 1
            await session.commit()
            logger.info("procurement: replaced %d offers for source=%s", rows, source)
            return rows

    async def count(self, source: Optional[str] = None, workspace_id: int = 1) -> int:
        async with AsyncSessionLocal() as session:
            stmt = sa_select(ProductOffer).where(ProductOffer.workspace_id == workspace_id)
            if source:
                stmt = stmt.where(ProductOffer.source == source)
            res = await session.execute(stmt)
            return len(res.scalars().all())

    async def search(
        self,
        query: str,
        limit: int = 10,
        in_stock_only: bool = False,
        workspace_id: int = 1,
        exclude: Optional[List[str]] = None,
    ) -> List[dict]:
        """Rank real offers against a free-text position query.

        Ranking (lower is better): exact article > article contains query >
        name match (more matched query tokens = better). Stopwords/1-char tokens
        are dropped so filler like "и"/"что" doesn't match everything. An
        accessory FOR a requested product ranks below the product itself.
        Ties broken by in-stock, **then by having a price at all** (a third of
        the site catalog syncs with price 0 — those rows used to win the
        price-ascending tie-break and crowd real, priced positions out of the
        result), then source priority, then price. Returns [] if nothing
        matches (caller must then say "не найдено" — never invent a position).

        ``exclude`` drops rows carrying terminology the client has ruled out
        («модульный не подходит») — see ``query_builder.build_search_query``.
        """
        q_norm = _norm(query)
        q_tokens = _expand_query_tokens(query)
        if not q_norm and not q_tokens:
            return []
        q_stems = {_stem(t) for t in q_tokens if len(t) >= 4}
        # Терминология, от которой клиент отказался («модульный не подходит»).
        # Без этого уточняющая реплика возвращала ровно то, что отвергли.
        excl_stems = [_stem(t) for x in (exclude or []) for t in _tokens(x) if len(t) >= 4]
        # The first significant word of a request is what is being asked for;
        # everything after it is usually a spec («контактор … катушка 220В» —
        # the coil voltage of a contactor, not a coil). Rows whose name starts
        # with that exact word rank above rows that merely mention it. Matched
        # in full, not stemmed, so «Контакт вспомогательный» can't claim a
        # «контактор» query.
        lead_tok = next((t for t in q_tokens if len(t) >= 4), "")
        q_amp = _amperage(query)
        has_sig_tokens = any(len(t) >= 4 for t in q_tokens)

        async with AsyncSessionLocal() as session:
            stmt = sa_select(ProductOffer).where(ProductOffer.workspace_id == workspace_id)
            if in_stock_only:
                stmt = stmt.where(ProductOffer.in_stock.is_(True))
            res = await session.execute(stmt)
            rows = res.scalars().all()

        scored = []
        for r in rows:
            art_norm = _norm(r.article)
            # include category so items with terse names (1C exports) stay findable
            name_low = (r.name or "").lower()
            if r.category:
                name_low = f"{name_low} {r.category.lower()}"
            if q_norm and art_norm and art_norm == q_norm:
                primary, misses = 0, 0
            elif len(q_norm) >= 4 and art_norm and q_norm in art_norm:
                primary, misses = 1, 0
            elif q_tokens:
                matched = sum(1 for t in q_tokens if _stem(t) in name_low)
                if not matched:
                    continue
                primary, misses = 2, len(q_tokens) - matched
            else:
                continue
            # significant matches: tokens len≥4 (short/stray ones like «из», com,
            # at don't count) — stem-matched, computed here where name_low is set.
            sig_matched = sum(1 for t in q_tokens if len(t) >= 4 and _stem(t) in name_low)
            # A row that hit nothing but a stray number («100» from «ТТИ-А 100/5»
            # matching «упаковка 100 шт.») is noise, not a candidate — but only
            # judge that when the query actually has a word to match; a pure
            # article query like "NXC 18" has no long tokens at all.
            if primary == 2 and has_sig_tokens and not sig_matched:
                continue
            # head match: name STARTS with a query term → it's that product, not
            # an accessory «…для преобразователей частоты». Ranks products first.
            head = 0 if any(len(t) >= 4 and name_low.startswith(_stem(t)) for t in q_tokens) else 1
            # «Катушка управления ДЛЯ КОНТАКТОРА» on a query for a contactor:
            # demote below the contactors regardless of how many query words it
            # happens to hit (it matches «катушка», «контактор» and the voltage).
            if excl_stems and any(e in name_low for e in excl_stems):
                continue
            name_words = _tokens(r.name or "")
            accessory = (
                1
                if _is_accessory_for_query(
                    name_low, _stem(name_words[0]) if name_words else "", q_stems
                )
                else 0
            )
            lead = 0 if lead_tok and name_low.startswith(lead_tok) else 1
            amp = _amp_bucket(q_amp, _amperage(r.name))
            # whole-word hits: a stem match is enough to be a candidate, but
            # «Контактный зажим» must not outrank «Контактор» on a contactor
            # query just because it is cheaper. Negated in the sort key.
            strong = sum(
                1 for t in q_tokens if len(t) >= 4 and any(w.startswith(t) for w in name_words)
            )
            scored.append((primary, accessory, lead, amp, -strong, misses, head, sig_matched, r))

        scored.sort(
            key=lambda x: (
                x[0],
                x[1],
                x[2],
                x[3],
                x[4],
                x[5],
                x[6],
                0 if x[8].in_stock else 1,
                0 if x[8].price else 1,
                SOURCE_PRIORITY.get(x[8].source, 9),
                x[8].price if x[8].price else float("inf"),
            )
        )
        labels = {0: "article_exact", 1: "article_partial", 2: "name"}
        top = scored[:limit]
        # ~11k site rows sync with price=0 (issue #841). They rank below equally
        # matching priced rows, but a tighter text match still wins — so a whole
        # page of results could carry no price at all and leave the assistant
        # unable to quote anything. Keep at least one priced position in view.
        if limit >= 2 and len(scored) > limit and not any(row[-1].price for row in top):
            priced = [row for row in scored[limit:] if row[-1].price][:1]
            if priced:
                top = top[: limit - 1] + priced

        out = []
        for primary, _acc, _lead, _amp, _strong, misses, head, sig_matched, r in top:
            d = r.to_dict()
            d["match"] = labels[primary]
            d["matched_tokens"] = (len(q_tokens) - misses) if primary == 2 else len(q_tokens)
            # confident = exact/partial article OR ≥2 significant name tokens —
            # spam subjects with a couple of incidental short hits aren't "ready".
            d["confident"] = primary in (0, 1) or sig_matched >= 2
            out.append(d)
        return out


offer_service = OfferService()
