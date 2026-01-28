# app/routers/__init__.py
"""API routers for admin and public endpoints."""

from app.routers import (
    audit,
    auth,
    chat,
    faq,
    llm,
    monitor,
    services,
    stt,
    telegram,
    tts,
    widget,
)


__all__ = [
    "auth",
    "audit",
    "services",
    "monitor",
    "faq",
    "stt",
    "llm",
    "tts",
    "chat",
    "telegram",
    "widget",
]
