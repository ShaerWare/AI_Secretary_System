"""USD→KZT rate for pricing (Мегазаказ USD price list).

Reestr rule 17: agent takes the rate from mig.kz; if it can't, it asks the
director (WhatsApp). The rate + date must appear in the КП. This service
fetches mig.kz's USD *buy* rate (matches the client's worked example), caches
it per day, and falls back to env / last-known with a `stale` flag so the
caller can trigger the director-confirmation path.
"""

import datetime
import logging
import os
import re

import httpx


logger = logging.getLogger(__name__)

MIG_URL = "https://mig.kz/"
# mig.kz rows are [buy][currency][sell]; the USD buy is the cell right before
# the USD currency cell.
_RATE_RE = re.compile(
    r'class="buy[^"]*">\s*([\d.]+)\s*</td>\s*<td class="currency">USD', re.IGNORECASE
)

# In-process cache: {"rate": float, "date": "YYYY-MM-DD", "source": str}
_cache: dict = {"rate": None, "date": None, "source": None}


def _today() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")


async def get_usd_kzt(force: bool = False) -> dict:
    """Return {rate, date, source, stale}.

    rate=None means no rate at all (caller must ask the director). stale=True
    means the value is a fallback, not a fresh mig.kz read — surface it and
    request confirmation before putting it in a КП.
    """
    today = _today()
    if _cache["rate"] and _cache["date"] == today and not force:
        return {**_cache, "stale": False}

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(MIG_URL)
            html = resp.text
        m = _RATE_RE.search(html)
        if m:
            rate = float(m.group(1))
            _cache.update(rate=rate, date=today, source="mig.kz")
            logger.info("USD/KZT rate from mig.kz: %s", rate)
            return {"rate": rate, "date": today, "source": "mig.kz", "stale": False}
        logger.warning("mig.kz: USD buy rate not found in page")
    except Exception as e:
        logger.warning("mig.kz rate fetch failed: %s", e)

    # fallbacks — flagged stale so the caller confirms with the director
    env_rate = os.getenv("PROCUREMENT_USD_KZT")
    if env_rate:
        try:
            return {"rate": float(env_rate), "date": today, "source": "env", "stale": True}
        except ValueError:
            pass
    if _cache["rate"]:
        return {**_cache, "stale": True}
    return {"rate": None, "date": today, "source": None, "stale": True}
