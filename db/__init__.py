"""
Database package for AI Secretary System.

Provides:
- SQLite for persistent storage (chat sessions, FAQ, presets, configs)
- Redis for caching and realtime data (sessions, metrics, rate limiting)
"""

from db.database import (
    AsyncSessionLocal,
    close_db,
    get_async_session,
    get_db_status,
    init_db,
)
from db.models import (
    PROVIDER_TYPES,
    AuditLog,
    Base,
    ChatMessage,
    ChatSession,
    CloudLLMProvider,
    FAQEntry,
    SystemConfig,
    TelegramSession,
    TTSPreset,
)
from db.redis_client import (
    close_redis,
    get_redis,
    redis_client,
)


__all__ = [
    # Database
    "get_async_session",
    "init_db",
    "close_db",
    "get_db_status",
    "AsyncSessionLocal",
    # Redis
    "get_redis",
    "close_redis",
    "redis_client",
    # Models
    "Base",
    "ChatSession",
    "ChatMessage",
    "FAQEntry",
    "TTSPreset",
    "SystemConfig",
    "TelegramSession",
    "AuditLog",
    "CloudLLMProvider",
    "PROVIDER_TYPES",
]
