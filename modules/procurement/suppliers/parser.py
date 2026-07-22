"""Config-driven readers: supplier price file -> raw rows.

Returns list of dicts with any of: article, name, price, stock, unit. The
adapter maps these to ProductOffer. Formats: `xlsx` (openpyxl), `pdf_lines`
(pdfplumber, 2-column "name .... price"). `xls`/complex-pdf added later.
"""

import logging
import re
from pathlib import Path
from typing import List, Optional

from modules.procurement.suppliers.registry import SUPPLIER_PRICES_DIR


logger = logging.getLogger(__name__)

_PRICE_TAIL_RE = re.compile(r"^(.*?)[\s ]+([\d\s .,]+)$")


def resolve_file(pattern: str) -> Optional[str]:
    """First file matching `pattern` under SUPPLIER_PRICES_DIR."""
    matches = sorted(Path(SUPPLIER_PRICES_DIR).glob(pattern))
    return str(matches[0]) if matches else None


def parse_number(raw) -> Optional[float]:
    """Parse '2 453', '1 400', '1,86', '5.3' -> float. None if not numeric."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).replace(" ", " ").strip()
    if not s:
        return None
    s = s.replace(" ", "")
    # comma as decimal separator when no dot present
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _read_xlsx(path: str, cfg: dict) -> List[dict]:
    import openpyxl

    rows: List[dict] = []
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    cols = cfg["cols"]
    header_row = cfg.get("header_row", -1)
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i <= header_row:
            continue
        name = row[cols["name"]] if cols["name"] < len(row) else None
        article = row[cols["article"]] if cols["article"] < len(row) else None
        if not name and not article:
            continue
        price = (
            parse_number(row[cols["price"]])
            if "price" in cols and cols["price"] < len(row)
            else None
        )
        unit = row[cols["unit"]] if "unit" in cols and cols["unit"] < len(row) else None
        rows.append(
            {
                "article": str(article).strip() if article else None,
                "name": str(name).strip() if name else None,
                "price": price,
                "unit": str(unit).strip() if unit else None,
            }
        )
    wb.close()
    return rows


def _read_xlsx_stock(path: str, cfg: dict) -> dict:
    """Read the stock-only file -> {article: stock_qty}. Skips warehouse labels."""
    import openpyxl

    scols = cfg["stock_cols"]
    data_row = cfg.get("stock_data_row", 0)
    out: dict = {}
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i < data_row:
            continue
        article = row[scols["article"]] if scols["article"] < len(row) else None
        stock = parse_number(row[scols["stock"]]) if scols["stock"] < len(row) else None
        # data rows have an article + numeric stock; warehouse labels don't
        if not article or stock is None:
            continue
        out[str(article).strip()] = stock
    wb.close()
    return out


def _read_pdf_lines(path: str, cfg: dict) -> List[dict]:
    """2-column price PDF: each product line is 'Name .... trailing_price'."""
    import pdfplumber

    rows: List[dict] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").splitlines():
                line = line.strip()
                if not line:
                    continue
                m = _PRICE_TAIL_RE.match(line)
                if not m:
                    continue
                name = m.group(1).strip()
                price = parse_number(m.group(2))
                # a real product line: has a name and a plausible price
                if not name or price is None or price <= 0:
                    continue
                rows.append({"article": None, "name": name, "price": price, "unit": None})
    return rows


def parse_supplier_file(cfg: dict) -> List[dict]:
    """Parse a supplier's price file (+ optional stock file) -> raw rows."""
    path = resolve_file(cfg["price_file"])
    if not path:
        raise FileNotFoundError(f"price file not found for {cfg['key']}: {cfg['price_file']}")

    fmt = cfg["format"]
    if fmt == "xlsx":
        rows = _read_xlsx(path, cfg)
    elif fmt == "pdf_lines":
        rows = _read_pdf_lines(path, cfg)
    else:
        raise ValueError(f"unsupported format {fmt} for {cfg['key']}")

    # Merge stock by article if a stock file is configured
    if cfg.get("stock_file"):
        spath = resolve_file(cfg["stock_file"])
        if spath:
            stock_map = _read_xlsx_stock(spath, cfg)
            for r in rows:
                if r.get("article") and r["article"] in stock_map:
                    r["stock"] = stock_map[r["article"]]

    logger.info("parsed %d rows for supplier %s from %s", len(rows), cfg["key"], Path(path).name)
    return rows
