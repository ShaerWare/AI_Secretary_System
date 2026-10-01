"""Кириллица и латиница в номиналах: «630А» и «630A» — одно и то же.

Реальный случай (30.09.2026): клиент прислал ссылку на «Автоматический ввод
резерва АВР NXZM-630S/3B 3P 630A», которого было 36 штук на складе, и спросил,
почему ассистент отвечает «наличие уточняется» и предлагает три других АВР.
Позиция не попадала в выдачу вообще: в её названии «630A» латиницей (U+0041), а
в запросе «630А» кириллицей (U+0410) — токен не находился, значимых совпадений
оставалось ноль, и строку отбрасывал фильтр случайных чисел.

Каталог расколот почти пополам: 11 501 позиция с кириллической А/Р/В после
цифры и 10 167 с латинской.
"""

import pytest_asyncio

import db.models  # noqa: F401  — registers every table so FKs resolve
from db.database import Base
from modules.core.models import Workspace
from modules.procurement.models import ProductOffer
from modules.procurement.service import OfferService, _fold


# name, article, in_stock — номиналы написаны то латиницей, то кириллицей,
# как в настоящем каталоге.
CATALOG = [
    ("Автоматический ввод резерва АВР NXZM-630S/3B 3P 630A", "256823", True),  # латиница
    ("Автоматический ввод резерва АВР NZ7-630S/3P 630А", "422190", None),  # кириллица
    ("Устройство АВР ТСР1 630А 3Р 230В EKF", "ats-tsr1-630A-3p-pro", None),
    ("Амперметр AMA-721 аналоговый на панель (72х72)", "ama-721", True),
    ("Амперметр AD-723 цифровой на панель (72х72)", "ad-723", True),
    ("Выключатель автоматический AV-6 1P 16A (B) 6kA", "mcb6-1-16B", True),  # латиница
    ("Выключатель автоматический ВА47-29 1Р 16А (С)", "va47-29-16", True),  # кириллица
]


@pytest_asyncio.fixture()
async def offers(test_engine, test_session_factory, monkeypatch):
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_factory() as session:
        session.add(Workspace(id=1, name="test", slug="test"))
        await session.flush()
        for i, (name, article, in_stock) in enumerate(CATALOG):
            session.add(
                ProductOffer(
                    source="site",
                    source_key=f"site#{i}",
                    article=article,
                    name=name,
                    price=100000.0 + i,
                    in_stock=in_stock,
                    workspace_id=1,
                )
            )
        await session.commit()

    monkeypatch.setattr("modules.procurement.service.AsyncSessionLocal", test_session_factory)
    return OfferService()


async def _names(svc, query, limit=6):
    return [o["name"] for o in await svc.search(query, limit=limit)]


def test_fold_maps_lookalikes_to_one_spelling():
    assert _fold("630а") == _fold("630a")
    assert _fold("3р") == _fold("3p")
    assert _fold("230в") == _fold("230b")
    # Буквы, которые НЕ омоглифы, трогать нельзя: «б» это не «6».
    assert _fold("б") == "б"


async def test_cyrillic_query_finds_latin_nameplate(offers):
    """Тот самый случай: запрос кириллицей, в названии латиница."""
    names = await _names(offers, "АВР 630А")
    assert "Автоматический ввод резерва АВР NXZM-630S/3B 3P 630A" in names
    assert names[0] == "Автоматический ввод резерва АВР NXZM-630S/3B 3P 630A"


async def test_latin_query_finds_cyrillic_nameplate(offers):
    names = await _names(offers, "АВР 630A")
    assert "Автоматический ввод резерва АВР NZ7-630S/3P 630А" in names


async def test_both_spellings_of_a_breaker_are_found(offers):
    """«16А» должно находить и латинское «16A», и кириллическое «16А»."""
    names = await _names(offers, "автоматический выключатель 16А")
    assert "Выключатель автоматический AV-6 1P 16A (B) 6kA" in names
    assert "Выключатель автоматический ВА47-29 1Р 16А (С)" in names


async def test_word_amper_does_not_turn_the_query_into_ammeters(offers):
    """«нужен АВР 630 ампер» выдавал АМПЕРМЕТРЫ: «ампер» был единственным
    значимым токеном и попадал в «амперметр», а «авр» и «630» короткие."""
    names = await _names(offers, "нужен АВР 630 ампер")
    assert names, "поиск ничего не вернул"
    assert not names[0].startswith("Амперметр"), names
    assert "Автоматический ввод резерва АВР NXZM-630S/3B 3P 630A" in names


async def test_ammeter_is_still_findable_when_actually_asked_for(offers):
    """Стоп-слово не должно похоронить сам товар «амперметр»."""
    names = await _names(offers, "амперметр на панель")
    assert any(n.startswith("Амперметр") for n in names), names


async def test_article_matches_across_spellings(offers):
    """Артикул с омоглифами ищется в любом написании."""
    names = await _names(offers, "ats-tsr1-630А-3p-pro")  # «А» кириллицей
    assert "Устройство АВР ТСР1 630А 3Р 230В EKF" in names
