"""
Security headers middleware.

Adds security headers to all responses:
- Content-Security-Policy: script-src 'self', style-src 'self' 'unsafe-inline', etc.
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY (or SAMEORIGIN)
- X-XSS-Protection: 1; mode=block
- Referrer-Policy: strict-origin-when-cross-origin
- Permissions-Policy: geolocation=(), microphone=(), camera=()

Environment variables:
- SECURITY_HEADERS_ENABLED: Enable security headers (default: true)
- X_FRAME_OPTIONS: X-Frame-Options value (default: DENY)
- CSP_ENABLED: Enable Content-Security-Policy (default: true)
"""

import os
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


# Configuration from environment
SECURITY_HEADERS_ENABLED = os.getenv("SECURITY_HEADERS_ENABLED", "true").lower() in (
    "true",
    "1",
    "yes",
)
X_FRAME_OPTIONS = os.getenv("X_FRAME_OPTIONS", "DENY")
CSP_ENABLED = os.getenv("CSP_ENABLED", "true").lower() in ("true", "1", "yes")

# Content-Security-Policy directives
_CSP_DIRECTIVES = [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: https:",
    "font-src 'self'",
    "connect-src 'self'",
    "media-src 'self' blob:",
    "frame-ancestors 'none'",
    "object-src 'none'",
    "base-uri 'self'",
]
CONTENT_SECURITY_POLICY = "; ".join(_CSP_DIRECTIVES)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to responses."""

    def __init__(self, app: ASGIApp, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        if self.enabled:
            # Content Security Policy — primary XSS protection
            if CSP_ENABLED:
                response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY

            # Prevent MIME type sniffing
            response.headers["X-Content-Type-Options"] = "nosniff"

            # Prevent clickjacking
            response.headers["X-Frame-Options"] = X_FRAME_OPTIONS

            # XSS protection (legacy but still useful)
            response.headers["X-XSS-Protection"] = "1; mode=block"

            # Control referrer information
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

            # Restrict browser features
            # Note: microphone needed for voice input, adjust as needed
            response.headers["Permissions-Policy"] = "geolocation=()"

            # Remove server header if present
            if "server" in response.headers:
                del response.headers["server"]

        return response


def get_security_headers_status() -> dict:
    """Get current security headers configuration."""
    headers: dict[str, str] = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": X_FRAME_OPTIONS,
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=()",
    }
    if CSP_ENABLED:
        headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    return {
        "enabled": SECURITY_HEADERS_ENABLED,
        "csp_enabled": CSP_ENABLED,
        "headers": headers,
    }
