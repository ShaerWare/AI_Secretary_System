"""Инъекция офферов в procurement-сессию: что видит клиент и откуда семантика.

Два свойства, каждое из которых уже ломалось на живых каналах:

1. семантический слой читает ВСЕ коллекции сессии. Раньше брался первый
   элемент пересечения с каталожными — и коллекция наличия (`stalker-stock`),
   привязанная рядом с каталогом, игнорировалась целиком;
2. клиентским каналам видны строки сайта и фида, но не дилерские строки
   поставщиков.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.chat import facade


OFFERS = [
    {
        "source": "site",
        "name": "Автомат сайта",
        "article": "A1",
        "price": 100.0,
        "currency": "KZT",
        "in_stock": True,
    },
    {
        "source": "feed",
        "name": "Автомат фида",
        "article": "A2",
        "price": 200.0,
        "currency": "KZT",
        "in_stock": True,
    },
    {
        "source": "supplier",
        "name": "Автомат поставщика",
        "article": "A3",
        "price": 50.0,
        "currency": "KZT",
        "supplier_name": "SunWell / EKF",
    },
]


@pytest.fixture()
def wired(monkeypatch):
    """Подменяем поиск, построитель запроса и контейнер — остаётся сама инъекция."""
    offer_service = MagicMock()
    offer_service.search = AsyncMock(return_value=list(OFFERS))
    monkeypatch.setattr("modules.procurement.service.offer_service", offer_service)
    monkeypatch.setattr(
        "modules.procurement.query_builder.build_search_query",
        AsyncMock(return_value=("автомат 16а", [])),
    )

    # Курс и расчёт цены менеджеру — не предмет этого теста, и `get_usd_kzt`
    # иначе полез бы на mig.kz.
    monkeypatch.setattr(
        "modules.procurement.rate_service.get_usd_kzt",
        AsyncMock(return_value={"rate": 540.0, "date": "2026-10-11", "source": "mig.kz"}),
    )
    monkeypatch.setattr(
        "modules.procurement.pricing.price_offer",
        AsyncMock(return_value={"ok": True, "purchase_price": 50.0, "client_price": 65.0}),
    )

    wiki = MagicMock()
    wiki.retrieve_multi_async = AsyncMock(return_value="описание из коллекций")
    container = MagicMock(wiki_rag_service=wiki)
    monkeypatch.setattr("app.dependencies.get_container", lambda: container)
    return wiki


async def test_semantic_context_reads_every_attached_collection(wired):
    """Коллекция наличия привязана рядом с каталогом — её нельзя пропускать."""
    await facade._inject_offer_context(None, "нужен автомат 16А", {"source": "widget"}, [6, 60])

    wired.retrieve_multi_async.assert_awaited_once()
    args, kwargs = wired.retrieve_multi_async.call_args
    assert args[1] == [6, 60]
    assert kwargs["top_k"] == 3


async def test_client_sees_site_and_feed_but_not_supplier_rows(wired):
    prompt = await facade._inject_offer_context(
        None, "нужен автомат 16А", {"source": "widget"}, [6, 60]
    )

    assert "Автомат сайта" in prompt
    assert "Автомат фида" in prompt
    # Дилерская цена и имя поставщика — только менеджеру.
    assert "Автомат поставщика" not in prompt
    assert "SunWell" not in prompt


async def test_manager_sees_supplier_rows(wired):
    prompt = await facade._inject_offer_context(
        None, "нужен автомат 16А", {"source": "admin"}, [6, 60]
    )

    assert "Автомат поставщика" in prompt


async def test_non_procurement_session_is_untouched(wired):
    """Инъекция opt-in: сессия без каталожной коллекции не трогается."""
    prompt = await facade._inject_offer_context(
        "исходный промпт", "нужен автомат 16А", {"source": "widget"}, [41]
    )

    assert prompt == "исходный промпт"
    wired.retrieve_multi_async.assert_not_awaited()


def test_rag_mode_all_never_enables_procurement():
    """«all» expands to every collection, catalog included — that must not turn a
    prompt-only assistant (Программист) into the StalkerElectric sales desk."""
    assert facade._is_procurement_session([1, 6, 60], "all") is False
    assert facade._is_procurement_session([6], "selected") is True
    assert facade._is_procurement_session([1, 60], "selected") is False
