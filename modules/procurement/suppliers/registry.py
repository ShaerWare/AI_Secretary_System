"""Per-supplier price-list configs.

Each supplier's file has its own layout, so parsing is config-driven (like
scrape_digitax SITES). Add a supplier = add a dict here (+ a custom hook only
for messy 1C/PDF layouts). `markup_pct` is uniform (20%) except own-brand
МегаЗаказ; the pricing engine (later) applies markup/VAT/rate — offers store
the raw source price + currency only.

Base dir via env SUPPLIER_PRICES_DIR (default matches the local drop folder).
"""

import os


SUPPLIER_PRICES_DIR = os.getenv("SUPPLIER_PRICES_DIR", "docs/файлысталкера")

# Uniform markup for all suppliers; МегаЗаказ overrides (own brand).
DEFAULT_MARKUP_PCT = 20
DEFAULT_VAT_PCT = 16

SUPPLIERS = [
    {
        "key": "sunwell",
        "name": "SunWell / EKF",
        "format": "xlsx",
        "price_file": "Диллер*.xlsx",
        "header_row": 10,  # 0-indexed row holding column titles
        "cols": {"article": 0, "name": 1, "price": 5, "unit": 4},
        # ОСТАТКИ file has stock only — merged into price rows by article.
        "stock_file": "ОСТАТКИ*.xlsx",
        "stock_data_row": 1,  # row 0 is a warehouse label
        "stock_cols": {"article": 0, "name": 1, "stock": 3},
        "currency": "KZT",
        "vat_included": False,
        "markup_pct": DEFAULT_MARKUP_PCT,
        "purchase_discount_pct": 0,
    },
    {
        "key": "xtrade",
        "name": "X-Trade KZ",
        "format": "pdf_lines",  # 2-column "Name .... price", no article
        "price_file": "X-Trade*.pdf",
        "has_article": False,
        "currency": "KZT",
        "vat_included": False,
        "markup_pct": DEFAULT_MARKUP_PCT,
        "purchase_discount_pct": 0,
    },
    # TODO (next increment): Электрокомплект .xls (1C, categories interspersed,
    # 2-row header) + Сталкер/МегаЗаказ lighting PDF (USD, categories). МегаЗаказ:
    # currency USD, vat_included False, markup 20, purchase_discount_pct 28.
]


def get_supplier(key: str) -> dict | None:
    for s in SUPPLIERS:
        if s["key"] == key:
            return s
    return None
