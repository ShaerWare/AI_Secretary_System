"""Client for the ARGS PIM API (ar-gs.ru) — where КП documents live.

Docs: GET {ARGS_PIM_URL}/openapi.json. Errors are always JSON
``{"error", "code", "field"}`` and decisions are taken on ``code``.

Some operations the secretary needs (prolong an offer, close it as lost,
change a draft) are not in the API yet. They are called anyway and a
``ROUTE_NOT_FOUND`` answer turns into :class:`PimNotSupported`, so the service
can fall back to what works today (reissue, local status). Once the PIM side
adds the method — see ``docs/pim-api-for-kp.md`` — the secretary starts using
it without a release.
"""

import asyncio
import logging
import os
from typing import Any, Optional

import httpx


logger = logging.getLogger(__name__)

DEFAULT_URL = "https://ar-gs.ru/api/v1"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class PimError(Exception):
    def __init__(self, message: str, code: str = "", status: int = 0, field: str = ""):
        super().__init__(message)
        self.code = code
        self.status = status
        self.field = field


class PimNotSupported(PimError):
    """The PIM has no such method (yet)."""


class PimNotConfigured(PimError):
    pass


def pim_settings() -> tuple[str, str]:
    url = (os.getenv("ARGS_PIM_URL") or DEFAULT_URL).rstrip("/")
    return url, (os.getenv("ARGS_PIM_API_KEY") or "").strip()


def is_configured() -> bool:
    return bool(pim_settings()[1])


class PimClient:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        # Env is read per call: the singleton is created at import, before .env
        # may be loaded, and the key can be rotated without a code change.
        self._base_url = base_url
        self._api_key = api_key

    @property
    def base_url(self) -> str:
        return (self._base_url or pim_settings()[0]).rstrip("/")

    @property
    def api_key(self) -> str:
        return self._api_key if self._api_key is not None else pim_settings()[1]

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
        raw: bool = False,
    ) -> Any:
        if not self.api_key:
            raise PimNotConfigured("PIM не подключён: не задан ARGS_PIM_API_KEY", "NOT_CONFIGURED")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        for attempt in range(2):
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                try:
                    resp = await client.request(
                        method, f"{self.base_url}{path}", json=json, params=params, headers=headers
                    )
                except httpx.HTTPError as e:
                    if attempt == 0:
                        await asyncio.sleep(2)
                        continue
                    raise PimError(f"PIM недоступен: {e}", "UNREACHABLE") from e
            if resp.status_code < 400:
                return resp.content if raw else resp.json()

            try:
                body = resp.json()
            except ValueError:
                body = {}
            code = body.get("code") or ""
            message = body.get("error") or f"PIM ответил {resp.status_code}"
            retry_after = resp.headers.get("Retry-After")
            # 429 — wait as told; 500/502 — the PIM says a retry may help.
            if attempt == 0 and (resp.status_code in (500, 502) or code == "RATE_LIMITED"):
                delay = min(float(retry_after or 2), 30.0) if retry_after else 2.0
                await asyncio.sleep(delay)
                continue
            error_cls = PimNotSupported if code == "ROUTE_NOT_FOUND" else PimError
            raise error_cls(message, code, resp.status_code, body.get("field") or "")
        raise PimError("PIM не ответил", "UNREACHABLE")

    # ─── Available today ─────────────────────────────────────

    async def me(self) -> dict:
        return await self._request("GET", "/me")

    async def list_offers(self, limit: int = 50, q: Optional[str] = None) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if q:
            params["q"] = q
        return await self._request("GET", "/offers", params=params)

    async def get_offer(self, offer_id: int) -> dict:
        return await self._request("GET", f"/offers/{offer_id}")

    async def create_offer(self, payload: dict) -> dict:
        return await self._request("POST", "/offers", json=payload)

    async def publish(self, offer_id: int) -> dict:
        return await self._request("POST", f"/offers/{offer_id}/publish")

    async def send_email(self, offer_id: int, payload: dict) -> dict:
        return await self._request("POST", f"/offers/{offer_id}/send-email", json=payload)

    async def pdf(self, offer_id: int) -> bytes:
        return await self._request("GET", f"/offers/{offer_id}/pdf", raw=True)

    # ─── Requested from the PIM side (docs/pim-api-for-kp.md) ─

    async def update_offer(self, offer_id: int, payload: dict) -> dict:
        """Change a draft or prolong an offer in place (same number, same link)."""
        return await self._request("PATCH", f"/offers/{offer_id}", json=payload)

    async def set_status(self, offer_id: int, status: str, reason: str = "") -> dict:
        return await self._request(
            "POST", f"/offers/{offer_id}/status", json={"status": status, "reason": reason}
        )

    async def delete_offer(self, offer_id: int) -> dict:
        return await self._request("DELETE", f"/offers/{offer_id}")


pim_client = PimClient()
