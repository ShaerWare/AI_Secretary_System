"""
Database package for AI Secretary System.

Provides:
- SQLite for persistent storage (chat sessions, FAQ, presets, configs)
- Redis for caching and realtime data (sessions, metrics, rate limiting)
"""

from db.database import (
    AsyncSessionLocal,
    Base,
    close_db,
    get_async_session,
    get_db_status,
    init_db,
    run_vacuum,
)
from db.redis_client import (
    close_redis,
    get_redis,
    redis_client,
)
from db.retry import get_busy_retry_count, retry_on_busy


def __getattr__(name: str):
    """Lazy import models from db.models to avoid circular imports."""
    import db.models as _models

    try:
        return getattr(_models, name)
    except AttributeError:
        raise AttributeError(f"module 'db' has no attribute {name!r}") from None


__all__ = [
    # Database
    "get_async_session",
    "init_db",
    "close_db",
    "get_db_status",
    "AsyncSessionLocal",
    "run_vacuum",
    # Retry
    "retry_on_busy",
    "get_busy_retry_count",
    # Redis
    "get_redis",
    "close_redis",
    "redis_client",
    # Models (lazy-loaded via __getattr__)
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
    # Sales bot models
    "BotAgentPrompt",
    "BotQuizQuestion",
    "BotSegment",
    "BotUserProfile",
    "BotFollowupRule",
    "BotFollowupQueue",
    "BotEvent",
    "BotTestimonial",
    "BotHardwareSpec",
    "BotAbTest",
    "BotDiscoveryResponse",
    "BotSubscriber",
    "BotGithubConfig",
]
