"""Наложение наличия из фида на строки каталога.

Фид делит с каталогом пространство артикулов (``vendorCode`` == ``sku``), и
наличие обновляется ПОВЕРХ строки сайта. Два свойства здесь критичны:

1. позиция, выпавшая из свежего фида (раскупили), теряет пометку — иначе она
   навсегда обещала бы склад, которого нет (§5.5);
2. меты товара, уже лежащие в ``extra``, при этом не затираются.
"""

import json

import pytest_asyncio

import db.models  # noqa: F401  — registers every table so FKs resolve
from db.database import Base
from modules.core.models import Workspace
from modules.procurement.models import ProductOffer
from modules.procurement.service import FEED_MARK, OfferService


SEEDED = [
    # (source_key, article, in_stock, stock_qty, extra)
    ("site#1", "271142", None, None, {"stock_blocks": ["EKF"]}),  # наличие неизвестно
    ("site#2", "300001", True, 5.0, {FEED_MARK: {"qty": 5, "as_of": "вчера"}}),  # вчерашний фид
    ("site#3", "400002", True, 9.0, None),  # наличие из мет каталога, фид её не знает
]


@pytest_asyncio.fixture()
async def service(test_engine, test_session_factory, monkeypatch):
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_factory() as session:
        session.add(Workspace(id=1, name="test", slug="test"))
        await session.flush()
        for key, article, in_stock, qty, extra in SEEDED:
            session.add(
                ProductOffer(
                    source="site",
                    source_key=key,
                    article=article,
                    name=f"Позиция {article}",
                    in_stock=in_stock,
                    stock_qty=qty,
                    extra=json.dumps(extra, ensure_ascii=False) if extra else None,
                    workspace_id=1,
                )
            )
        await session.commit()

    monkeypatch.setattr("modules.procurement.service.AsyncSessionLocal", test_session_factory)
    return OfferService()


async def _rows(test_session_factory):
    from sqlalchemy import select

    async with test_session_factory() as session:
        res = await session.execute(select(ProductOffer).order_by(ProductOffer.source_key))
        return {r.article: r for r in res.scalars().all()}


async def test_overlay_marks_feed_rows_and_drops_yesterdays(service, test_session_factory):
    items = [
        {"article": "271142", "stock_qty": 40.0, "lead_time_days": 3},
        {"article": "999777", "stock_qty": 2.0, "lead_time_days": 1},  # нет в каталоге
    ]

    result = await service.apply_feed_stock(items, as_of="2026-10-11 19:11")

    assert result["updated"] == 1
    assert result["matched_articles"] == {"271142"}
    # Непопавший артикул вызывающий пишет отдельным источником.
    assert "999777" not in result["matched_articles"]

    rows = await _rows(test_session_factory)

    # Было «наличие уточняется» — фид подтвердил остаток и срок.
    fresh = rows["271142"]
    assert fresh.in_stock is True
    assert fresh.stock_qty == 40.0
    assert fresh.lead_time_days == 3
    extra = json.loads(fresh.extra)
    assert extra[FEED_MARK]["as_of"] == "2026-10-11 19:11"
    assert extra["stock_blocks"] == ["EKF"]  # меты каталога не затёрты

    # Вчерашний фид её уже не перечисляет → пометка снята, а не оставлена.
    sold_out = rows["300001"]
    assert sold_out.in_stock is None
    assert sold_out.stock_qty is None
    assert sold_out.extra is None
    assert result["cleared"] == 1


async def test_rows_without_feed_mark_keep_catalog_stock(service, test_session_factory):
    """Наличие из мет каталога фид не трогает: он добавляет знание, а не отменяет."""
    await service.apply_feed_stock(
        [{"article": "271142", "stock_qty": 1.0, "lead_time_days": 2}], as_of="now"
    )

    untouched = (await _rows(test_session_factory))["400002"]
    assert untouched.in_stock is True
    assert untouched.stock_qty == 9.0


async def test_empty_feed_changes_nothing(service, test_session_factory):
    """Пустой разбор не должен обнулять наличие всему каталогу."""
    result = await service.apply_feed_stock([], as_of="now")

    assert result == {"updated": 0, "cleared": 0, "matched_articles": set()}
    rows = await _rows(test_session_factory)
    assert rows["300001"].in_stock is True
