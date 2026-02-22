# app/routers/__init__.py
"""API routers for admin and public endpoints."""

from app.routers import (
    amocrm,
    audit,
    auth,
    backup,
    bot_sales,
    chat,
    claude_code,
    faq,
    github_webhook,
    gsm,
    kanban,
    legal,
    llm,
    monitor,
    roles,
    services,
    telegram,
    usage,
    whatsapp,
    widget,
    wiki_rag,
    yoomoney_webhook,
)


# STT router is optional (requires torch/vosk/whisper)
try:
    from app.routers import stt
except ImportError:
    stt = None  # type: ignore[assignment]

# TTS router is optional (requires torch for XTTS)
try:
    from app.routers import tts
except ImportError:
    tts = None  # type: ignore[assignment]


__all__ = [
    "amocrm",
    "auth",
    "audit",
    "backup",
    "services",
    "monitor",
    "faq",
    "kanban",
    "roles",
    "stt",
    "llm",
    "tts",
    "chat",
    "claude_code",
    "telegram",
    "usage",
    "widget",
    "gsm",
    "bot_sales",
    "legal",
    "whatsapp",
    "wiki_rag",
    "github_webhook",
    "yoomoney_webhook",
]
