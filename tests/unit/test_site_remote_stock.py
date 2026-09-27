"""Наличие и срок поставки с сайта: мета `_remote_stock_blocks`.

Карточка товара на stalkerelectric.kz показывает блок «Наличие · Удалённый
склад · 2 шт. Срок поставки 1-2 дн.» — это остатки поставщика, которые сайт
хранит в мете `_remote_stock_blocks`. Адаптер её игнорировал, и единственные
настоящие данные о наличии, которые у нас вообще есть, пропадали; у остальных
карточек в этом месте написано «По запросу» — не «нет», а «уточняется».
"""

import json

from modules.procurement.site_adapter import _availability, _to_offer


BLOCK = {
    "warehouse": "Удалённый склад",
    "supplier": "PRSTH",
    "qty": 2,
    "lead_time_min": 1,
    "lead_time_max": 2,
}


def _product(meta_value, **kw):
    p = {
        "id": 109832,
        "name": "Редуктор червячный INNORED IRWD075-50-80B14",
        "sku": "IRWD075-50-80B14",
        "price": "107340",
        "stock_status": "instock",
        "manage_stock": False,
        "stock_quantity": None,
        "meta_data": [{"key": "_remote_stock_blocks", "value": meta_value}],
    }
    p.update(kw)
    return p


def test_filled_block_gives_stock_and_lead_time():
    a = _availability(_product([BLOCK]))
    assert a["in_stock"] is True
    assert a["stock_qty"] == 2
    assert a["lead_time_days"] == 2, "обещать срок короче максимального нельзя"


def test_block_may_arrive_json_encoded():
    a = _availability(_product(json.dumps([BLOCK])))
    assert a["in_stock"] is True and a["stock_qty"] == 2


def test_several_warehouses_sum_up_and_take_worst_lead_time():
    second = {**BLOCK, "warehouse": "Склад 2", "qty": 5, "lead_time_max": 7}
    a = _availability(_product([BLOCK, second]))
    assert a["stock_qty"] == 7
    assert a["lead_time_days"] == 7


def test_empty_block_is_on_request_not_out_of_stock():
    """«По запросу» в карточке — это «уточняется», а не подтверждённое «нет»."""
    a = _availability(_product([]))
    assert a["in_stock"] is None
    assert a["lead_time_days"] is None


def test_missing_meta_falls_back_to_unknown():
    p = _product([])
    p["meta_data"] = []
    assert _availability(p)["in_stock"] is None


def test_default_instock_status_is_still_not_a_claim():
    """У всех 30 тыс. товаров stock_status='instock' по умолчанию — это не наличие."""
    p = _product([])
    p["meta_data"] = []
    p["stock_status"] = "instock"
    assert _availability(p)["in_stock"] is None


def test_explicit_out_of_stock_status_is_honoured():
    p = _product([])
    p["stock_status"] = "outofstock"
    assert _availability(p)["in_stock"] is False


def test_malformed_block_does_not_crash():
    assert _availability(_product("не json"))["in_stock"] is None
    assert _availability(_product([{"qty": "два"}]))["in_stock"] is None


def test_offer_carries_stock_lead_time_and_raw_blocks():
    o = _to_offer(_product([BLOCK]))
    assert o["in_stock"] is True
    assert o["lead_time_days"] == 2
    assert o["extra"]["remote_stock"][0]["supplier"] == "PRSTH"
