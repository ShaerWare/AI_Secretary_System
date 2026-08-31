"""Follow-up requests must not search on the words the client rejected.

Real failure (01.09.2026): after «модульный не подходит, нам нужен промышленный
тип» the search ran on that raw sentence, «модульный» was its strongest token,
and the assistant answered «в каталоге только модульные модели» while 556 power
contactors sat in the catalog.
"""

import pytest_asyncio

import db.models  # noqa: F401  — registers every table so FKs resolve
from db.database import Base
from modules.core.models import Workspace
from modules.procurement.models import ProductOffer
from modules.procurement.query_builder import _extract_json, build_search_query
from modules.procurement.service import OfferService


class FakeLLM:
    """Stands in for the provider: records the prompt, returns a canned answer."""

    def __init__(self, answer):
        self.answer = answer
        self.messages = None

    def generate_response_from_messages(self, messages, **kwargs):
        self.messages = messages
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


HISTORY = [
    {"role": "user", "content": "Контактор модульный NCH8-20/20 20А есть в наличии?"},
    {"role": "assistant", "content": "Да, есть — 5 432 ₸"},
]
FOLLOW_UP = "модульный не подходит, нам нужен промышленный тип"


async def test_follow_up_is_rewritten_and_exclusion_extracted():
    llm = FakeLLM('{"query": "контактор силовой", "exclude": ["модульный"]}')
    query, exclude = await build_search_query(llm, HISTORY, FOLLOW_UP)
    assert query == "контактор силовой"
    assert exclude == ["модульный"]
    # the whole dialogue is handed over, not just the last line
    assert "NCH8-20/20" in llm.messages[-1]["content"]


async def test_first_message_skips_the_llm_call():
    """No prior turns → the raw text IS the request; don't pay for a rewrite."""
    llm = FakeLLM('{"query": "нечто иное", "exclude": []}')
    query, exclude = await build_search_query(llm, [], "нужен контактор 18А")
    assert (query, exclude) == ("нужен контактор 18А", [])
    assert llm.messages is None


async def test_current_message_already_persisted_still_counts_as_first():
    llm = FakeLLM('{"query": "x", "exclude": []}')
    history = [{"role": "user", "content": "нужен контактор 18А"}]
    query, _ = await build_search_query(llm, history, "нужен контактор 18А")
    assert query == "нужен контактор 18А"
    assert llm.messages is None


async def test_unusable_answer_falls_back_to_raw_message():
    llm = FakeLLM("извините, не понял вопроса")
    assert await build_search_query(llm, HISTORY, FOLLOW_UP) == (FOLLOW_UP, [])


async def test_llm_failure_never_breaks_the_chat():
    llm = FakeLLM(RuntimeError("bridge timeout"))
    assert await build_search_query(llm, HISTORY, FOLLOW_UP) == (FOLLOW_UP, [])


async def test_missing_llm_falls_back():
    assert await build_search_query(None, HISTORY, FOLLOW_UP) == (FOLLOW_UP, [])


def test_extract_json_tolerates_fences_and_prose():
    assert _extract_json('```json\n{"query": "кабель"}\n```') == {"query": "кабель"}
    assert _extract_json('Вот результат: {"query": "кабель"} — готово') == {"query": "кабель"}
    assert _extract_json("совсем не json") is None
    assert _extract_json("[1, 2]") is None


CATALOG = [
    (
        "Контактор модульный NCH8-20/20 20А 2НО АС220/230В 50Гц",
        5432.7,
        "Контакторы, Модульное оборудование",
    ),
    ("Контактор NXC-18 18A 220В/АС3 1НО+1НЗ 50Гц", 6237.4, "Контакторы, Силовое оборудование"),
    (
        "Контактор КМЭ малогабаритный 18А 220В 1NO EKF PROxima",
        4448.6,
        "Контакторы, Силовое оборудование",
    ),
]


@pytest_asyncio.fixture()
async def offers(test_engine, test_session_factory, monkeypatch):
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with test_session_factory() as session:
        session.add(Workspace(id=1, name="test", slug="test"))
        await session.flush()
        for i, (name, price, category) in enumerate(CATALOG):
            session.add(
                ProductOffer(
                    source="site",
                    source_key=f"site#{i}",
                    name=name,
                    price=price,
                    in_stock=True,
                    category=category,
                    workspace_id=1,
                )
            )
        await session.commit()
    monkeypatch.setattr("modules.procurement.service.AsyncSessionLocal", test_session_factory)
    return OfferService()


async def test_excluded_terminology_is_dropped_from_results(offers):
    names = [o["name"] for o in await offers.search("контактор силовой", exclude=["модульный"])]
    assert names, "search returned nothing"
    assert not any("модульный" in n for n in names), names


async def test_promyshlennyy_maps_to_the_power_category(offers):
    """The catalog has no word «промышленный» — the split lives in the category."""
    names = [o["name"] for o in await offers.search("контактор промышленный")]
    assert names[0] != "Контактор модульный NCH8-20/20 20А 2НО АС220/230В 50Гц", names
