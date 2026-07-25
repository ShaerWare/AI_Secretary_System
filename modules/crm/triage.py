"""amoCRM triage — turn unanswered (unsorted) leads into an actionable list.

The client's pain #2: incoming requests pile up unanswered (37 commercials /
40M ₸ with no touches). This orchestration reads unsorted leads and, for each,
routes the request (which supplier per category), searches the offer base and
prices matches, and proposes an action — so the manager reviews a ready list
instead of triaging by hand. Nothing is sent automatically (Reestr rule 7).

v1 uses the lead name/subject as the request text; pulling the full email/chat
body per lead is a later refinement.
"""

import logging

from app.services.amocrm_service import get_unsorted_leads
from modules.procurement.pricing import price_offer
from modules.procurement.rate_service import get_usd_kzt
from modules.procurement.routing import route
from modules.procurement.service import offer_service


logger = logging.getLogger(__name__)


async def triage_unanswered(config: dict, limit: int = 20) -> dict:
    """Fetch unsorted leads and enrich each with routing + priced matches.

    `config` must carry a valid `subdomain` + `access_token` (caller resolves
    the token). Returns {ok, count, leads:[{lead_id, name, category, routing,
    matches, suggestion}]}.
    """
    data = await get_unsorted_leads(
        config["subdomain"], config["access_token"], limit=min(limit, 250)
    )
    leads = data.get("_embedded", {}).get("leads", [])[:limit]
    rate_info = await get_usd_kzt()

    out = []
    for lead in leads:
        name = (lead.get("name") or "").strip()
        body = (lead.get("_body") or "").strip()
        # Match/КП on the SUBJECT (precise — a long body dilutes relevance and
        # matches random tokens). Route on subject+body (category recall). Body
        # is shown to the manager for context.
        route_query = f"{name} {body}".strip()[:500]
        routing = route(route_query) if route_query else {"suppliers": [], "category": None}
        matches_raw = await offer_service.search(name, limit=3) if name else []

        # keep only confident matches (guards against spam subjects matching a
        # single stray token and falsely reading as "ready to quote")
        matches = []
        for o in matches_raw:
            if not o.get("confident"):
                continue
            if o["source"] == "supplier":
                p = await price_offer(o, rate_info=rate_info)
                client_price = p.get("client_price") if p.get("ok") else None
            else:
                client_price = o.get("price")
            matches.append(
                {
                    "name": o.get("name"),
                    "article": o.get("article"),
                    "client_price": client_price,
                    "in_stock": o.get("in_stock"),
                    "source": o.get("source"),
                }
            )

        if matches:
            suggestion = "есть позиции — подготовить черновик КП"
        elif routing.get("suppliers"):
            names = ", ".join(s["name"] for s in routing["suppliers"])
            suggestion = f"в базе нет — запросить у: {names}"
        else:
            suggestion = "нет совпадений в базе — проверить вручную (спам или редкая позиция)"

        out.append(
            {
                "lead_id": lead.get("id"),
                "name": name,
                "body_preview": body[:200],
                "category": lead.get("_unsorted_category"),
                "source": lead.get("_unsorted_source"),
                "created_at": lead.get("created_at"),
                "routing": routing,
                "matches": matches,
                "suggestion": suggestion,
            }
        )

    return {"ok": True, "count": len(out), "leads": out}
