"""КП (коммерческое предложение) builder — priced offers -> quote document.

Assembles a client-facing quote from real, priced supplier/site offers. Applies
the client's Reestr rules:
- prices = client price from the pricing engine (markup + VAT already applied);
- suppliers are never named to the client (rule 6); Мегазаказ goes as Stalker
  Electric own brand (rule 19);
- zero-margin lines are flagged for the director, not silently quoted (rule 16);
- USD rate + date shown when any line came from a USD price list (rule 17);
- delivery-by-actual-weight + price validity lines (rule 13);
- it's a DRAFT — nothing goes to the client without director approval (rule 7).
"""

import logging
from typing import Optional

from modules.procurement.pricing import price_offer
from modules.procurement.rate_service import get_usd_kzt
from modules.procurement.service import offer_service


logger = logging.getLogger(__name__)

DELIVERY_LINE = "Доставка рассчитывается по фактическому весу и габаритам груза при отгрузке."


def _fmt(n: float) -> str:
    """12 345.67 -> '12 345.67' (thin-space thousands, trim .00)."""
    s = f"{n:,.2f}".replace(",", " ")
    return s[:-3] if s.endswith(".00") else s


def build_kp(
    line_items: list[dict],
    *,
    client_name: Optional[str] = None,
    quote_date: Optional[str] = None,
    valid_days: int = 5,
) -> dict:
    """Assemble a КП from priced line items.

    `line_items`: [{"offer": dict, "qty": number, "pricing": dict}] — pricing
    from ``price_offer``. Returns a structured dict + rendered ``markdown``.
    Lines without a valid price (or zero-margin) go to ``flags`` and are left
    out of the totals (director must resolve them).
    """
    rows: list[dict] = []
    flags: list[str] = []
    total = 0.0
    rate_used: Optional[dict] = None

    for it in line_items:
        offer = it.get("offer") or {}
        qty = it.get("qty") or 1
        pricing = it.get("pricing") or {}
        name = offer.get("name") or "—"
        if not pricing.get("ok"):
            flags.append(
                f"«{name}»: нет расчёта цены ({pricing.get('reason')}) — уточнить у поставщика"
            )
            continue
        if pricing.get("zero_margin_flag"):
            flags.append(f"«{name}»: закупка ≥ цены продажи — согласовать наценку с директором")
            continue
        unit = pricing["client_price"]
        line_sum = round(unit * qty, 2)
        total += line_sum
        if pricing.get("rate"):
            rate_used = pricing
        rows.append(
            {
                "n": len(rows) + 1,
                "name": name,
                "article": offer.get("article"),
                "qty": qty,
                "unit_price": unit,
                "sum": line_sum,
                "in_stock": offer.get("in_stock"),
            }
        )

    total = round(total, 2)
    total_no_vat = round(total / 1.16, 2)
    vat = round(total - total_no_vat, 2)

    md = _render_markdown(
        rows, total, total_no_vat, vat, client_name, quote_date, rate_used, valid_days
    )
    return {
        "ok": bool(rows),
        "rows": rows,
        "total_with_vat": total,
        "total_no_vat": total_no_vat,
        "vat": vat,
        "currency": "KZT",
        "rate": rate_used,
        "flags": flags,
        "markdown": md,
    }


def _render_markdown(
    rows, total, total_no_vat, vat, client_name, quote_date, rate_used, valid_days
) -> str:
    out = ["## Коммерческое предложение — Stalker Electric"]
    if client_name:
        out.append(f"**Заказчик:** {client_name}")
    if quote_date:
        out.append(f"**Дата:** {quote_date}")
    out.append("")
    out.append("| № | Наименование | Артикул | Кол-во | Цена за ед., ₸ | Сумма, ₸ | Наличие |")
    out.append("|---|---|---|---|---|---|---|")
    for r in rows:
        stock = "в наличии" if r["in_stock"] else ("под заказ" if r["in_stock"] is False else "—")
        art = r["article"] or "—"
        out.append(
            f"| {r['n']} | {r['name']} | {art} | {r['qty']:g} | "
            f"{_fmt(r['unit_price'])} | {_fmt(r['sum'])} | {stock} |"
        )
    out.append("")
    out.append(f"**Итого без НДС:** {_fmt(total_no_vat)} ₸")
    out.append(f"**НДС 16%:** {_fmt(vat)} ₸")
    out.append(f"**Итого с НДС:** {_fmt(total)} ₸")
    out.append("")
    if rate_used and rate_used.get("rate"):
        stale = " (предварительный, уточняется)" if rate_used.get("rate_stale") else ""
        out.append(
            f"_Курс USD/KZT: {rate_used['rate']} на {rate_used.get('rate_date')} "
            f"({rate_used.get('rate_source')}){stale}._"
        )
    out.append(f"_{DELIVERY_LINE}_")
    out.append(f"_Цены действительны {valid_days} рабочих дней._")
    return "\n".join(out)


async def build_kp_for_queries(
    items: list[dict], *, client_name: Optional[str] = None, quote_date: Optional[str] = None
) -> dict:
    """Resolve [{"query": str, "qty": number}] -> priced offers -> КП.

    Each query is matched to the top offer via the unified search; unresolved
    queries are reported in ``unresolved``.
    """
    rate_info = await get_usd_kzt()
    line_items: list[dict] = []
    unresolved: list[str] = []
    for req in items:
        query = (req.get("query") or "").strip()
        qty = req.get("qty") or 1
        if not query:
            continue
        matches = await offer_service.search(query, limit=1)
        if not matches:
            unresolved.append(query)
            continue
        offer = matches[0]
        pricing = (
            await price_offer(offer, rate_info=rate_info)
            if offer["source"] == "supplier"
            else {"ok": True, "client_price": offer.get("price"), "zero_margin_flag": False}
        )
        line_items.append({"offer": offer, "qty": qty, "pricing": pricing})

    kp = build_kp(line_items, client_name=client_name, quote_date=quote_date)
    kp["unresolved"] = unresolved
    return kp
