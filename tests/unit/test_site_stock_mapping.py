"""Наличие с сайта: не выдавать умолчание WooCommerce за подтверждённый остаток.

В каталоге stalkerelectric.kz учёт остатков выключен — у всех 30 163 товаров
``manage_stock: false`` и ``stock_quantity: null``, а ``stock_status`` равен
"instock" по умолчанию. Раньше это писалось в базу как ``in_stock=True``, и
ассистент отвечал клиенту «✅ В наличии» про любую позицию каталога.
"""

import pytest

from modules.procurement.site_adapter import _stock


@pytest.mark.parametrize(
    "product,expected",
    [
        # магазин остатки не ведёт — наличие неизвестно, а не «есть»
        ({"stock_status": "instock", "manage_stock": False, "stock_quantity": None}, None),
        # явное «нет в наличии» — это факт
        ({"stock_status": "outofstock", "manage_stock": False, "stock_quantity": None}, False),
        ({"stock_status": "onbackorder", "manage_stock": True, "stock_quantity": 0}, False),
        # учёт включён и остаток положительный — наличие подтверждено
        ({"stock_status": "instock", "manage_stock": True, "stock_quantity": 7}, True),
        ({"stock_status": "instock", "manage_stock": True, "stock_quantity": 0}, False),
        # поля вообще не пришли
        ({}, None),
    ],
)
def test_stock_mapping(product, expected):
    assert _stock(product) is expected
