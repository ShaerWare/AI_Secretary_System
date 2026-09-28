"""Наличие и срок поставки с сайта: пер-поставщиковые меты товара.

После смены темы (28.09.2026) магазин пишет остатки по полю на склад и срок
рядом: `EKF_Stock_0` + `EKF_Stock_0_delivery` («1-2 дня»), `Chint_Stock_0` +
«3-4 дня», `Axima_Stock_0`/`Axima_Stock_2` + «1 день».

Читать сводку `_remote_stock_blocks` больше нельзя: срок в ней прибит
константой «1-2 дн.» для каждого поставщика (у Chint собственное поле говорит
«3-4 дня» — так в 39 случаях из 40), а количество расходится с исходными
полями в 67 случаях из 77. Сводке оставлен только ПРОМСИТЕХ, у которого своих
полей нет, и срок оттуда не берётся.
"""

import json

from modules.procurement.site_adapter import _availability, _delivery_days, _to_offer


def _product(meta: dict, **kw):
    p = {
        "id": 97896,
        "name": "Дифференциальный автомат NXBLE-63 2P C63 30mA",
        "sku": "819983",
        "price": "6347",
        "stock_status": "instock",
        "manage_stock": False,
        "stock_quantity": None,
        "meta_data": [{"key": k, "value": v} for k, v in meta.items()],
    }
    p.update(kw)
    return p


def test_delivery_string_takes_the_upper_bound():
    """Обещать быстрее, чем сказал поставщик, нельзя."""
    assert _delivery_days("1 день") == 1
    assert _delivery_days("1-2 дня") == 2
    assert _delivery_days("3-4 дня") == 4
    assert _delivery_days("уточняется") is None
    assert _delivery_days(None) is None


def test_supplier_stock_gives_quantity_and_its_own_lead_time():
    a = _availability(_product({"Chint_Stock_0": "54", "Chint_Stock_0_delivery": "3-4 дня"}))
    assert a["in_stock"] is True
    assert a["stock_qty"] == 54
    assert a["lead_time_days"] == 4, "срок Chint — 3-4 дня, а не константа сводки"


def test_two_warehouses_of_one_supplier_sum_up():
    a = _availability(
        _product(
            {
                "Axima_Stock_0": "3",
                "Axima_Stock_2": "5",
                "Axima_Stock_0_delivery": "1 день",
                "Axima_Stock_2_delivery": "1 день",
            }
        )
    )
    assert a["stock_qty"] == 8
    assert a["lead_time_days"] == 1


def test_fastest_supplier_with_stock_wins():
    """Склады разных поставщиков не суммируются: иначе «12 шт. за 2 дня»
    означало бы, что приедут и те семь, что лежат у четырёхдневного."""
    a = _availability(
        _product(
            {
                "EKF_Stock_0": "5",
                "EKF_Stock_0_delivery": "1-2 дня",
                "Chint_Stock_0": "7",
                "Chint_Stock_0_delivery": "3-4 дня",
            }
        )
    )
    assert a["in_stock"] is True
    assert a["stock_qty"] == 5, "показываем остаток самого быстрого, а не сумму"
    assert a["lead_time_days"] == 2


def test_supplier_without_stock_is_skipped():
    a = _availability(
        _product(
            {
                "Axima_Stock_0": "0",
                "Axima_Stock_2": "0",
                "Axima_Stock_0_delivery": "1 день",
                "Chint_Stock_0": "12",
                "Chint_Stock_0_delivery": "3-4 дня",
            }
        )
    )
    assert a["stock_qty"] == 12
    assert a["lead_time_days"] == 4


def test_all_known_suppliers_at_zero_is_not_a_refusal():
    """Позицию может возить тот, чьих полей на сайте нет, — это «уточняется»."""
    a = _availability(_product({"Axima_Stock_0": "0", "Axima_Stock_2": "0"}))
    assert a["in_stock"] is None
    assert a["lead_time_days"] is None


def test_stale_summary_never_overrides_supplier_fields():
    """Сводка уверяет, что у AXIMA 28 шт., хотя оба её склада дают ноль."""
    a = _availability(
        _product(
            {
                "Axima_Stock_0": "0",
                "Axima_Stock_2": "0",
                "_remote_stock_blocks": [
                    {
                        "warehouse": "Удалённый склад",
                        "supplier": "AXIMA",
                        "qty": 28,
                        "lead_time_min": 1,
                        "lead_time_max": 2,
                    },
                ],
            }
        )
    )
    assert a["in_stock"] is None
    assert a["stock_qty"] is None


def test_summary_is_used_only_for_suppliers_without_their_own_fields():
    """ПРОМСИТЕХ живёт только в сводке — остаток берём, срок нет."""
    a = _availability(
        _product(
            {
                "_remote_stock_blocks": [
                    {
                        "warehouse": "Удалённый склад",
                        "supplier": "PRSTH",
                        "qty": 2,
                        "lead_time_min": 1,
                        "lead_time_max": 2,
                    },
                ],
            }
        )
    )
    assert a["in_stock"] is True
    assert a["stock_qty"] == 2
    assert a["lead_time_days"] is None, "срок в сводке — константа, а не данные"


def test_summary_json_encoded_is_parsed():
    blocks = [{"supplier": "PRSTH", "qty": 3, "lead_time_min": 1, "lead_time_max": 2}]
    a = _availability(_product({"_remote_stock_blocks": json.dumps(blocks)}))
    assert a["in_stock"] is True and a["stock_qty"] == 3


def test_default_instock_status_is_still_not_a_claim():
    """У всех 30 тыс. товаров stock_status='instock' по умолчанию."""
    assert _availability(_product({}))["in_stock"] is None


def test_explicit_out_of_stock_status_is_honoured():
    assert _availability(_product({}, stock_status="outofstock"))["in_stock"] is False


def test_malformed_values_do_not_crash():
    assert _availability(_product({"_remote_stock_blocks": "не json"}))["in_stock"] is None
    assert _availability(_product({"EKF_Stock_0": "две штуки"}))["in_stock"] is None
    assert (
        _availability(_product({"_remote_stock_blocks": [{"supplier": "PRSTH"}]}))["in_stock"]
        is None
    )


def test_offer_carries_stock_lead_time_and_raw_readings():
    o = _to_offer(_product({"Chint_Stock_0": "54", "Chint_Stock_0_delivery": "3-4 дня"}))
    assert o["in_stock"] is True
    assert o["lead_time_days"] == 4
    assert o["extra"]["suppliers"][0]["supplier"] == "Chint"
