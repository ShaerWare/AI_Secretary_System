"""
Rate limiting configuration using slowapi.

Environment variables:
- RATE_LIMIT_ENABLED: Enable rate limiting (default: true)
- RATE_LIMIT_DEFAULT: Default rate limit (default: "60/minute")
- RATE_LIMIT_AUTH: Rate limit for auth endpoints (default: "10/minute")
- RATE_LIMIT_CHAT: Rate limit for chat endpoints (default: "30/minute")
- RATE_LIMIT_TTS: Rate limit for TTS endpoints (default: "20/minute")
"""

import os

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def get_real_client_ip(request: Request) -> str:
    """Get client IP, considering proxy headers."""
    # Check for forwarded headers (reverse proxy)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take the first IP in the chain (original client)
        return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fallback to direct connection
    return get_remote_address(request)


# Check if rate limiting is enabled
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() in ("true", "1", "yes")

# Rate limit configurations
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "60/minute")
RATE_LIMIT_AUTH = os.getenv("RATE_LIMIT_AUTH", "10/minute")
RATE_LIMIT_CHAT = os.getenv("RATE_LIMIT_CHAT", "30/minute")
RATE_LIMIT_TTS = os.getenv("RATE_LIMIT_TTS", "20/minute")
RATE_LIMIT_STT = os.getenv("RATE_LIMIT_STT", "20/minute")


def create_limiter() -> Limiter:
    """Create and configure the rate limiter."""
    return Limiter(
        key_func=get_real_client_ip,
        default_limits=[RATE_LIMIT_DEFAULT] if RATE_LIMIT_ENABLED else [],
        enabled=RATE_LIMIT_ENABLED,
    )


# Global limiter instance
limiter = create_limiter()


def get_limiter() -> Limiter:
    """Get the global limiter instance."""
    return limiter


# Decorator shortcuts for common rate limits
def limit_auth(func):
    """Rate limit for authentication endpoints."""
    if RATE_LIMIT_ENABLED:
        return limiter.limit(RATE_LIMIT_AUTH)(func)
    return func


def limit_chat(func):
    """Rate limit for chat endpoints."""
    if RATE_LIMIT_ENABLED:
        return limiter.limit(RATE_LIMIT_CHAT)(func)
    return func


def limit_tts(func):
    """Rate limit for TTS endpoints."""
    if RATE_LIMIT_ENABLED:
        return limiter.limit(RATE_LIMIT_TTS)(func)
    return func


def limit_stt(func):
    """Rate limit for STT endpoints."""
    if RATE_LIMIT_ENABLED:
        return limiter.limit(RATE_LIMIT_STT)(func)
    return func


def get_rate_limit_status() -> dict:
    """Get current rate limit configuration status."""
    return {
        "enabled": RATE_LIMIT_ENABLED,
        "limits": {
            "default": RATE_LIMIT_DEFAULT,
            "auth": RATE_LIMIT_AUTH,
            "chat": RATE_LIMIT_CHAT,
            "tts": RATE_LIMIT_TTS,
            "stt": RATE_LIMIT_STT,
        },
    }
