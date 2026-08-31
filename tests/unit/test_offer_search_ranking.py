"""Ranking regression tests for the unified offer search.

All four cases below are taken from a real failure (01.09.2026): a client asked
for a contactor, the catalog had one in stock with a price, and the assistant
answered «самих контакторов нет — только катушки управления».
"""

import pytest
import pytest_asyncio

import db.models  # noqa: F401  — registers every table so FKs resolve
from db.database import Base
from modules.core.models import Workspace
from modules.procurement.models import ProductOffer
from modules.procurement.service import (
    OfferService,
    _expand_query_tokens,
    _is_accessory_for_query,
    _stem,
)


# name, price, in_stock, category
CATALOG = [
    ("Контактор NXC-18 18A 220В/АС3 1НО+1НЗ 50Гц", 6237.4, True, "Контакторы"),
    ("Контактор NXC-32 32A 48В/АС3 1НО+1НЗ 50Гц", 0.0, True, "Контакторы"),
    ("Катушка управления для контактора NXC-06-22 48AC 50/60Гц", 0.0, True, "Контакторы"),
    ("Катушка управления КТЭ F 185А-225А 220В EKF PROxima", 12487.8, True, None),
    ("Контакт дополнительный XB-2 NO зеленый EKF PROxima", 390.0, True, None),
    ("Контактный зажим (упаковка 100 шт.)", 293.8, True, None),
    (
        "Колодка 2 гн. 10А 2,2кВт б/з Эксперт EKF PROxima",
        549.9,
        True,
        "Электроустановочные изделия",
    ),
    ("Удлинитель Эксперт 2 гнезда 2 метра 10А/2,2кВт", 1411.8, True, "Электроустановочные изделия"),
]


@pytest_asyncio.fixture()
async def offers(test_engine, test_session_factory, monkeypatch):
    """Seed a miniature catalog and point the service at the test DB."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_factory() as session:
        session.add(Workspace(id=1, name="test", slug="test"))
        await session.flush()
        for i, (name, price, in_stock, category) in enumerate(CATALOG):
            session.add(
                ProductOffer(
                    source="site",
                    source_key=f"site#{i}",
                    name=name,
                    price=price,
                    in_stock=in_stock,
                    category=category,
                    workspace_id=1,
                )
            )
        await session.commit()

    monkeypatch.setattr("modules.procurement.service.AsyncSessionLocal", test_session_factory)
    return OfferService()


async def _names(svc, query, limit=5):
    return [o["name"] for o in await svc.search(query, limit=limit)]


async def test_contactor_query_returns_contactors_not_coils(offers):
    """«катушка 220В» is the contactor's coil voltage, not a request for coils."""
    names = await _names(
        offers, "Подбери контактор из наличия, мне нужен на 18,5 квт, катушка 220В"
    )
    assert names, "search returned nothing for a contactor query"
    assert names[0].startswith("Контактор"), names


async def test_priced_row_outranks_zero_price_row(offers):
    """A third of the site catalog syncs with price 0 — it must not crowd out
    positions that actually have a price."""
    names = await _names(offers, "бытовой контактор")
    assert names[0] == "Контактор NXC-18 18A 220В/АС3 1НО+1НЗ 50Гц", names
    assert "Контактор NXC-32 32A 48В/АС3 1НО+1НЗ 50Гц" in names


async def test_contactor_outranks_auxiliary_contact(offers):
    """«Контакт дополнительный» / «Контактный зажим» share a stem with
    «контактор» and are cheaper — they must not win on the price tie-break."""
    names = await _names(offers, "бытовой контактор")
    assert names[0].startswith("Контактор"), names


async def test_motor_query_does_not_return_socket_blocks(offers):
    """«электродвигатель» must not stem down to «электр» and match every
    «Электроустановочное изделие» in the catalog."""
    names = await _names(
        offers, "Помоги мне найти контактор на 7,5 квт электродвигатель из наличия"
    )
    assert names, "search returned nothing"
    assert names[0].startswith("Контактор"), names
    assert not any(n.startswith(("Колодка", "Удлинитель")) for n in names), names


async def test_coil_query_still_returns_coils(offers):
    """The accessory demotion must not fire when the accessory IS the request."""
    names = await _names(offers, "катушка управления для контактора NXC-18")
    assert names[0].startswith("Катушка"), names


async def test_no_match_returns_empty(offers):
    """Never invent a position: nothing relevant → empty result."""
    assert await offers.search("трансформатор тока ТТИ-А 100/5") == []


@pytest.mark.parametrize(
    "word,expected",
    [
        ("электродвигатель", "электродвига"),
        ("контактор", "контакт"),
        ("катушка", "катушк"),
        ("кабель", "кабель"),
    ],
)
def test_stem_keeps_long_words_distinct(word, expected):
    assert _stem(word) == expected


def test_request_filler_is_dropped():
    tokens = _expand_query_tokens("Помоги мне найти контактор на 7,5 квт из наличия")
    assert tokens == ["контактор"]


def test_accessory_detection_respects_the_request():
    name = "катушка управления для контактора nxc-06-22"
    # asking for a contactor → the coil is an accessory
    assert _is_accessory_for_query(name, "катушк", {"контакт"}) is True
    # asking for the coil itself → not demoted
    assert _is_accessory_for_query(name, "катушк", {"катушк", "контакт"}) is False
