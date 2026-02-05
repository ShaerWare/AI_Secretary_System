# app/routers/__init__.py
"""API routers for admin and public endpoints."""

from app.routers import (
    audit,
    auth,
    bot_sales,
    chat,
    faq,
    github_webhook,
    gsm,
    llm,
    monitor,
    services,
    stt,
    telegram,
    tts,
    usage,
    widget,
    yoomoney_webhook,
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
    "usage",
    "widget",
    "gsm",
    "bot_sales",
    "github_webhook",
    "yoomoney_webhook",
]
