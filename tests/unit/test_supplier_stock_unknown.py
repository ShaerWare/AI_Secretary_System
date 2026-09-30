"""«Остаток не указан» ≠ «нет в наличии».

Реальный случай (08.09.2026): в базе 19 936 из 20 728 позиций SunWell/EKF
лежали с ``in_stock=False``, хотя поставщик про них ничего не говорил — файл
ОСТАТКИ перечисляет только то, что ЕСТЬ (838 артикулов). Через совпадение по
артикулу это метило «НЕТ в наличии» 15 892 позиции каталога сайта, и ассистент
отказывал клиенту по товарам, которые поставляются.

Заодно проверяем обратную сторону: позиции сайта, найденные в прайсе
поставщика, должны подсказывать ассистенту уточнять только СРОК.
"""

import pytest
import pytest_asyncio

import db.models  # noqa: F401  — registers every table so FKs resolve
from db.database import Base
from modules.chat.facade import _supply_label
from modules.core.models import Workspace
from modules.procurement.models import ProductOffer
from modules.procurement.service import OfferService
from modules.procurement.suppliers.adapter import _row_to_offer


CFG = {"key": "sunwell", "name": "SunWell / EKF", "currency": "KZT", "markup_pct": 30}


def test_missing_stock_column_is_unknown_not_out_of_stock():
    """Строка прайса без данных об остатке — «не знаем», а не «нет»."""
    offer = _row_to_offer({"article": "A1", "name": "Автомат", "price": 100.0}, CFG, 0)
    assert offer["in_stock"] is None
    assert offer["stock_qty"] is None


def test_explicit_zero_stock_is_out_of_stock():
    offer = _row_to_offer({"article": "A1", "name": "Автомат", "stock": 0}, CFG, 0)
    assert offer["in_stock"] is False


def test_positive_stock_is_in_stock():
    offer = _row_to_offer({"article": "A1", "name": "Автомат", "stock": 7}, CFG, 0)
    assert offer["in_stock"] is True
    assert offer["stock_qty"] == 7


@pytest.mark.parametrize("manager", [True, False])
def test_supply_label_never_claims_stock_without_data(manager):
    assert _supply_label(None, manager) == "наличие уточняется"


def test_supply_label_asks_only_about_lead_time_when_supplier_has_it():
    label = _supply_label(
        {"available": True, "supplier_name": "SunWell / EKF", "qty": 12, "as_of": "2026-07-24"},
        False,
    )
    assert "есть у поставщика" in label
    assert "срок" in label
    assert "SunWell" not in label, "имя поставщика клиенту раскрывать нельзя"


def test_supply_label_shows_supplier_and_stock_to_manager():
    label = _supply_label(
        {"available": True, "supplier_name": "SunWell / EKF", "qty": 12, "as_of": "2026-07-24"},
        True,
    )
    assert "SunWell / EKF" in label and "12" in label and "2026-07-24" in label


def test_supply_label_unknown_stock_in_price_list():
    label = _supply_label({"available": None, "supplier_name": "X", "as_of": None}, False)
    assert "прайсе поставщика" in label and "срок" in label


@pytest_asyncio.fixture()
async def svc(test_engine, test_session_factory, monkeypatch):
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with test_session_factory() as session:
        session.add(Workspace(id=1, name="test", slug="test"))
        await session.flush()
        session.add_all(
            [
                # каталог сайта: остатки не ведутся никогда
                ProductOffer(
                    source="site",
                    source_key="site#1",
                    article="819983",
                    name="Дифференциальный автомат NXBLE-63 2P C63 30mA",
                    price=6347.0,
                    in_stock=None,
                    workspace_id=1,
                ),
                ProductOffer(
                    source="site",
                    source_key="site#2",
                    article="999999",
                    name="Дифференциальный автомат NXBLE-32 2P C32 30mA",
                    price=4100.0,
                    in_stock=None,
                    workspace_id=1,
                ),
                # прайс поставщика: остаток есть только по первому артикулу
                ProductOffer(
                    source="supplier",
                    source_key="sunwell#1",
                    supplier_name="SunWell / EKF",
                    article="819983",
                    name="NXBLE-63 2P C63 30mA",
                    price=3900.0,
                    in_stock=True,
                    stock_qty=12,
                    workspace_id=1,
                ),
            ]
        )
        await session.commit()
    monkeypatch.setattr("modules.procurement.service.AsyncSessionLocal", test_session_factory)
    return OfferService()


async def test_site_offer_is_annotated_with_supplier_availability(svc):
    offers = await svc.search("дифференциальный автомат NXBLE", limit=5)
    by_art = {o["article"]: o for o in offers if o["source"] == "site"}
    assert by_art["819983"]["supply"]["available"] is True
    assert by_art["819983"]["supply"]["supplier_name"] == "SunWell / EKF"
    assert by_art["819983"]["supply"]["qty"] == 12
    # позиции без совпадения в прайсах остаются «наличие уточняется»
    assert by_art["999999"].get("supply") is None


async def test_duplicate_source_key_does_not_break_the_sync(svc):
    """Пагинация WooCommerce может отдать один товар дважды — синк не должен падать.

    Прод, 25.09.2026: суточный синк каталога упал на
    `UNIQUE constraint failed: product_offers.source, product_offers.source_key`
    и сутки остались без обновления.
    """
    from modules.procurement.models import SOURCE_SITE

    written = await svc.replace_source_offers(
        SOURCE_SITE,
        [
            {"source_key": 555, "name": "Автомат A", "price": 100.0},
            {"source_key": 555, "name": "Автомат A (та же строка со второй страницы)"},
            {"source_key": 556, "name": "Автомат B"},
        ],
    )
    assert written == 2, "дубль source_key должен схлопнуться, а не уронить синк"


async def test_resync_over_existing_rows_does_not_hit_unique(svc):
    """Апсерт, а не «удалить и вставить»: ключ с прошлого прогона не роняет синк.

    Прод, ночь 29.09.2026: синк SunWell/EKF свалился на первой же строке
    `sunwell#0`, оставшейся с предыдущего дня — 20 728 позиций крупнейшего
    поставщика сутки стояли непересчитанными.
    """
    from modules.procurement.models import SOURCE_SUPPLIER

    batch = [
        {"source_key": "sunwell#0", "name": "Автомат AV-6 1P 10A", "price": 2453.0},
        {"source_key": "sunwell#1", "name": "Автомат AV-6 1P 16A", "price": 2500.0},
    ]
    assert await svc.replace_source_offers(SOURCE_SUPPLIER, batch, scope_key="sunwell") == 2
    # Тот же набор второй раз — прежний порядок падал на UNIQUE.
    assert await svc.replace_source_offers(SOURCE_SUPPLIER, batch, scope_key="sunwell") == 2


async def test_resync_updates_price_instead_of_duplicating(svc):
    from modules.procurement.models import SOURCE_SUPPLIER

    await svc.replace_source_offers(
        SOURCE_SUPPLIER,
        [{"source_key": "sunwell#0", "name": "Автомат", "price": 100.0, "in_stock": True}],
        scope_key="sunwell",
    )
    await svc.replace_source_offers(
        SOURCE_SUPPLIER,
        [{"source_key": "sunwell#0", "name": "Автомат", "price": 250.0}],
        scope_key="sunwell",
    )
    rows = await svc.search("автомат", limit=10)
    mine = [o for o in rows if o["source_key"] == "sunwell#0"]
    assert len(mine) == 1, "строка должна обновиться, а не продублироваться"
    assert mine[0]["price"] == 250.0
    assert mine[0]["in_stock"] is None, "поля, которых нет в новой строке, тоже переписываются"


async def test_rows_missing_from_the_new_batch_are_dropped(svc):
    """Пропала позиция у поставщика — пропала и из поиска."""
    from modules.procurement.models import SOURCE_SUPPLIER

    await svc.replace_source_offers(
        SOURCE_SUPPLIER,
        [
            {"source_key": "sunwell#0", "name": "Автомат остался"},
            {"source_key": "sunwell#1", "name": "Автомат пропал"},
        ],
        scope_key="sunwell",
    )
    await svc.replace_source_offers(
        SOURCE_SUPPLIER,
        [{"source_key": "sunwell#0", "name": "Автомат остался"}],
        scope_key="sunwell",
    )
    names = [o["name"] for o in await svc.search("автомат", limit=10)]
    assert "Автомат остался" in names
    assert "Автомат пропал" not in names


async def test_scope_key_does_not_touch_a_neighbour_supplier(svc):
    """Прогон одного поставщика не должен вычищать чужие строки."""
    from modules.procurement.models import SOURCE_SUPPLIER

    await svc.replace_source_offers(
        SOURCE_SUPPLIER, [{"source_key": "aksima#0", "name": "Реле Аксима"}], scope_key="aksima"
    )
    await svc.replace_source_offers(
        SOURCE_SUPPLIER, [{"source_key": "sunwell#0", "name": "Реле Санвел"}], scope_key="sunwell"
    )
    names = [o["name"] for o in await svc.search("реле", limit=10)]
    assert "Реле Аксима" in names and "Реле Санвел" in names
