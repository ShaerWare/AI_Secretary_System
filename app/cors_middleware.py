"""
Dynamic CORS middleware.

Combines static CORS_ORIGINS from env with allowed_domains
from widget instances in the database. Widget domains are cached
with a TTL and automatically refreshed.

Usage:
    from app.cors_middleware import DynamicCORSMiddleware, get_cors_middleware

    app.add_middleware(DynamicCORSMiddleware, static_origins=["https://example.com"])

    # After widget CRUD — invalidate cache so new domains take effect immediately
    get_cors_middleware().invalidate_cache()
"""

import logging
import time
from typing import Optional, Set

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Receive, Scope, Send


logger = logging.getLogger(__name__)

# Module-level reference for cache invalidation from other modules
_instance: Optional["DynamicCORSMiddleware"] = None


def get_cors_middleware() -> Optional["DynamicCORSMiddleware"]:
    """Get the active DynamicCORSMiddleware instance."""
    return _instance


class DynamicCORSMiddleware:
    """CORS middleware that dynamically includes widget allowed_domains."""

    CACHE_TTL = 60.0  # seconds

    # Origins used by Capacitor mobile apps (Android/iOS WebView)
    MOBILE_ORIGINS = {
        "capacitor://localhost",
        "https://localhost",
        "http://localhost",
    }

    def __init__(self, app: ASGIApp, static_origins: list[str] | None = None) -> None:
        global _instance
        self.app = app
        self.allow_all = static_origins is not None and "*" in static_origins
        self.static_origins: Set[str] = set(self.MOBILE_ORIGINS)
        if static_origins and not self.allow_all:
            self.static_origins |= {o.lower().rstrip("/") for o in static_origins}
        self._widget_origins: Set[str] = set()
        self._cache_ts: float = 0.0
        _instance = self

    async def _ensure_widget_origins(self) -> Set[str]:
        """Return cached widget origins, refreshing if stale."""
        now = time.time()
        if now - self._cache_ts >= self.CACHE_TTL:
            await self._refresh_widget_origins()
        return self._widget_origins

    async def _refresh_widget_origins(self) -> None:
        """Load allowed_domains from all widget instances."""
        origins: Set[str] = set()
        try:
            from db.integration import async_widget_instance_manager

            instances = await async_widget_instance_manager.list_instances()
            for inst in instances:
                for domain in inst.get("allowed_domains", []):
                    d = domain.strip().lower().rstrip("/")
                    if not d:
                        continue
                    if d.startswith("https://") or d.startswith("http://"):
                        # Already a full origin (e.g. "https://shaerware.digital")
                        origins.add(d)
                    else:
                        # Bare domain (e.g. "shaerware.digital")
                        origins.add(f"https://{d}")
                        origins.add(f"http://{d}")
        except Exception as e:
            logger.debug(f"Could not load widget origins: {e}")
        self._widget_origins = origins
        self._cache_ts = time.time()
        if origins:
            logger.debug(f"CORS widget origins refreshed: {origins}")

    def invalidate_cache(self) -> None:
        """Force refresh on next request (call after widget CRUD)."""
        self._cache_ts = 0.0

    def _is_allowed(self, origin: str, widget_origins: Set[str]) -> bool:
        if self.allow_all:
            return True
        o = origin.lower().rstrip("/")
        return o in self.static_origins or o in widget_origins

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        origin = headers.get("origin")

        if not origin:
            await self.app(scope, receive, send)
            return

        widget_origins = await self._ensure_widget_origins()

        # Preflight (OPTIONS)
        if scope["method"] == "OPTIONS":
            if self._is_allowed(origin, widget_origins):
                request_headers = headers.get("access-control-request-headers", "*")
                preflight_headers = [
                    (b"access-control-allow-origin", origin.encode()),
                    (
                        b"access-control-allow-methods",
                        b"DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT",
                    ),
                    (b"access-control-allow-headers", request_headers.encode()),
                    (b"access-control-allow-credentials", b"true"),
                    (b"access-control-max-age", b"600"),
                    (b"vary", b"Origin"),
                    (b"content-length", b"0"),
                ]
                await send(
                    {"type": "http.response.start", "status": 200, "headers": preflight_headers}
                )
                await send({"type": "http.response.body", "body": b""})
            else:
                body = b"Disallowed CORS origin"
                await send(
                    {
                        "type": "http.response.start",
                        "status": 400,
                        "headers": [
                            (b"content-type", b"text/plain; charset=utf-8"),
                            (b"content-length", str(len(body)).encode()),
                            (b"vary", b"Origin"),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
            return

        # Normal request — add CORS headers to response
        allowed = self._is_allowed(origin, widget_origins)

        async def send_with_cors(message: dict) -> None:
            if message["type"] == "http.response.start" and allowed:
                resp_headers = MutableHeaders(scope=message)
                resp_headers.append("access-control-allow-origin", origin)
                resp_headers.append("access-control-allow-credentials", "true")
                resp_headers.append("vary", "Origin")
            await send(message)

        await self.app(scope, receive, send_with_cors)
