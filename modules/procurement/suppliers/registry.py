"""Per-supplier price-list configs.

Column maps come from the client's Reestr v3 (sheet "5. Структура файлов",
0-indexed, verified July 2026). Parsing is config-driven (like scrape_digitax
SITES). `markup_pct` = per-supplier КП coefficient from Reestr sheet "2.
Ценообразование" (КП = закупка × factor). The pricing engine (later) applies
markup/VAT/USD-rate; offers store the raw source price + currency only.

Base dir via env SUPPLIER_PRICES_DIR (default matches the local drop folder).
"""

import os


SUPPLIER_PRICES_DIR = os.getenv("SUPPLIER_PRICES_DIR", "docs/файлысталкера")

DEFAULT_VAT_PCT = 16

SUPPLIERS = [
    {
        "key": "sunwell",
        "name": "SunWell / EKF",
        "format": "xlsx",
        "price_file": "Диллер*.xlsx",
        "header_row": 10,  # титулы в строке 11 (1-idx), данные с 12
        "cols": {"article": 0, "name": 1, "price": 5, "unit": 4},  # 5 = «Дил»
        # ОСТАТКИ file has stock only — merged into price rows by article.
        "stock_file": "ОСТАТКИ*.xlsx",
        "stock_data_row": 1,  # row 0 is a warehouse label
        "stock_cols": {"article": 0, "name": 1, "stock": 3},
        "currency": "KZT",
        "vat_included": True,
        "markup_pct": 30,  # закупка × 1.30
        "purchase_discount_pct": 0,
    },
    {
        "key": "aksima",
        "name": "AXIMA / Chint (Аксима)",
        "format": "xlsx",
        "price_file": "аксима*.xlsx",
        "header_row": 5,  # шапка 3–6, данные с 7 (1-idx)
        # 0=article, 7=name, 13=дилерская цена, 14/15=остатки ВТО/Теректы
        "cols": {"article": 0, "name": 7, "price": 13, "stock": 14, "stock2": 15},
        "currency": "KZT",
        "vat_included": True,  # цены уже с НДС
        "markup_pct": 30,  # КП = max(РРЦ Chint, закупка × 1.30)
        "purchase_discount_pct": 0,
    },
    {
        "key": "aksima_chint_rrc",
        "name": "Chint (РРЦ, через Аксиму)",
        "format": "xlsx",
        "price_file": "Остатки_и_доступность*.xlsx",
        "header_row": 8,  # шапка 7–9, данные с 10 (1-idx)
        # 0=article, 2=name, 6=unit, 8=цена РРЦ, 11=доступно
        "cols": {"article": 0, "name": 2, "unit": 6, "price": 8, "stock": 11},
        "currency": "KZT",
        "vat_included": True,
        "markup_pct": 0,  # цена в КП = РРЦ из файла как есть
        "purchase_discount_pct": 30,  # закупка = РРЦ × 0.70
    },
    {
        "key": "xtrade",
        "name": "X-Trade KZ",
        "format": "pdf_lines",  # 2-column "Name .... price", no article
        "price_file": "X-Trade*.pdf",
        "has_article": False,
        "currency": "KZT",
        "vat_included": True,
        "markup_pct": 40,  # закупка × 1.40
        "purchase_discount_pct": 0,
    },
    {
        "key": "elektrokomplekt",
        "name": "ЭКТ Атырау (Электрокомплект)",
        "format": "xls",  # 1C export: categories interspersed with products
        "price_file": "Электрокомплект*.xls",
        "header_row": 10,  # шапка 1–11, данные с 12 (1-idx)
        # 1=дерево категорий, 2=article, 3=цена «регион», 5=«розница»
        "cols": {"article": 2, "name": 1, "price": 3},
        "require_article": True,
        "category_col": 1,
        "currency": "KZT",
        "vat_included": True,
        "markup_pct": 25,  # закупка × 1.25 по умолчанию (не фиксирована: 15–35%)
        "purchase_discount_pct": 0,
    },
    {
        "key": "megazakaz",
        "name": "Мегазаказ (свет, бренд Stalker Electric)",
        "format": "pdf_table",  # 4-col table: name/model/size/price, categories in col0
        "price_file": "Сталкер прайс*.pdf",
        "cols": {"article": 1, "size": 2, "price": 3},  # model = article
        "category_col": 0,
        "currency": "USD",  # цены в $ и БЕЗ НДС
        "vat_included": False,
        "markup_pct": 20,  # КП = $ × курс × 1.20 × 1.16
        "purchase_discount_pct": 28,  # закупка = $ × курс × 0.72
    },
]


def get_supplier(key: str) -> dict | None:
    for s in SUPPLIERS:
        if s["key"] == key:
            return s
    return None
