"""
Database integration helpers for orchestrator.

Provides backward-compatible wrapper classes that match the old API
while using the new database repositories internally.
"""

import hashlib
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from db.database import AsyncSessionLocal, close_db, get_db_status, init_db
from db.redis_client import close_redis, get_redis_status, init_redis
from db.repositories import (
    AmoCRMConfigRepository,
    AmoCRMSyncLogRepository,
    AuditRepository,
    BotInstanceRepository,
    ChatRepository,
    CloudProviderRepository,
    ConfigRepository,
    FAQRepository,
    GSMCallLogRepository,
    GSMSMSLogRepository,
    KnowledgeDocumentRepository,
    PaymentRepository,
    PresetRepository,
    TelegramRepository,
    UserRepository,
    WidgetInstanceRepository,
)


logger = logging.getLogger(__name__)


# ============== Database Manager ==============


class DatabaseManager:
    """
    Singleton manager for database operations.
    Provides async context managers for repository access.
    """

    _instance = None
    _initialized = False

    def __new__(cls) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(self) -> None:
        """Initialize database and Redis connections."""
        if self._initialized:
            return

        logger.info("🗄️ Initializing database...")
        await init_db()

        logger.info("🔴 Initializing Redis...")
        redis_ok = await init_redis()
        if not redis_ok:
            logger.warning("⚠️ Redis not available, caching disabled")

        self._initialized = True
        logger.info("✅ Database ready")

    async def shutdown(self) -> None:
        """Close all connections."""
        await close_db()
        await close_redis()
        self._initialized = False
        logger.info("🗄️ Database connections closed")

    async def get_status(self) -> dict:
        """Get database and Redis status for health checks."""
        db_status = await get_db_status()
        redis_status = await get_redis_status()
        return {
            "database": {
                "sqlite": db_status,
                "redis": redis_status,
            }
        }


# Global database manager
db_manager = DatabaseManager()


# ============== Chat Manager (Backward-Compatible) ==============


class AsyncChatManager:
    """
    Async-compatible ChatManager that uses database.
    Provides same API as the old synchronous ChatManager for easy migration.
    """

    def _generate_id(self) -> str:
        return f"chat_{int(time.time() * 1000)}"

    def _generate_message_id(self) -> str:
        ts = str(time.time())
        return f"msg_{int(time.time() * 1000)}_{hashlib.md5(ts.encode()).hexdigest()[:6]}"

    async def list_sessions(self, owner_id: Optional[int] = None) -> List[dict]:
        """List all sessions with summary info."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.list_sessions(owner_id=owner_id)

    async def get_session(self, session_id: str, owner_id: Optional[int] = None) -> Optional[dict]:
        """Get full session with messages."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.get_session(session_id, owner_id=owner_id)

    async def create_session(
        self,
        title: Optional[str] = None,
        system_prompt: Optional[str] = None,
        source: Optional[str] = None,
        source_id: Optional[str] = None,
        owner_id: Optional[int] = None,
    ) -> dict:
        """Create new session."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.create_session(
                title, system_prompt, source, source_id, owner_id=owner_id
            )

    async def update_session(
        self,
        session_id: str,
        title: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> Optional[dict]:
        """Update session title or system prompt."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.update_session(session_id, title, system_prompt)

    async def delete_session(self, session_id: str, owner_id: Optional[int] = None) -> bool:
        """Delete session."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.delete_session(session_id, owner_id=owner_id)

    async def delete_sessions_bulk(
        self, session_ids: List[str], owner_id: Optional[int] = None
    ) -> int:
        """Delete multiple sessions by ID list."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.delete_sessions_bulk(session_ids, owner_id=owner_id)

    async def list_sessions_grouped(self, owner_id: Optional[int] = None) -> dict:
        """Get sessions grouped by source."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.list_sessions_grouped(owner_id=owner_id)

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> Optional[dict]:
        """Add message to session."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.add_message(session_id, role, content)

    async def edit_message(
        self,
        session_id: str,
        message_id: str,
        content: str,
    ) -> Optional[dict]:
        """Edit message."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.edit_message(session_id, message_id, content)

    async def delete_message(
        self,
        session_id: str,
        message_id: str,
    ) -> bool:
        """Delete message and all subsequent messages."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.delete_message(session_id, message_id)

    async def count_messages(
        self,
        session_id: str,
        role: str,
        since: datetime,
    ) -> int:
        """Count messages in a session by role since a given time."""
        from sqlalchemy import func, select

        from db.models import ChatMessage

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(func.count())
                .select_from(ChatMessage)
                .where(
                    ChatMessage.session_id == session_id,
                    ChatMessage.role == role,
                    ChatMessage.created >= since,
                )
            )
            return result.scalar() or 0

    async def get_messages_for_llm(
        self,
        session_id: str,
        system_prompt: Optional[str] = None,
    ) -> List[dict]:
        """Get messages in LLM format."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.get_messages_for_llm(session_id, system_prompt)


# ============== FAQ Manager ==============


class AsyncFAQManager:
    """Async FAQ manager using database with caching."""

    async def get_all(self) -> Dict[str, str]:
        """Get all FAQ as question->answer dict."""
        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)
            return await repo.get_as_dict()

    async def get_all_entries(self) -> List[dict]:
        """Get all FAQ entries with full details."""
        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)
            return await repo.get_all_entries(enabled_only=False)

    async def find_answer(self, question: str) -> Optional[str]:
        """Find exact match answer for question."""
        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)
            return await repo.find_answer(question)

    async def add(self, question: str, answer: str) -> dict:
        """Add new FAQ entry."""
        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)
            return await repo.create_entry(question, answer)

    async def update(self, old_question: str, question: str, answer: str) -> Optional[dict]:
        """Update FAQ entry."""
        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)

            # If question changed, need to find by old and delete + create
            if old_question != question:
                existing = await repo.get_by_question(old_question)
                if existing:
                    await repo.delete_by_question(old_question)
                return await repo.create_entry(question, answer)
            else:
                existing = await repo.get_by_question(question)
                if existing:
                    return await repo.update_entry(
                        existing["id"],
                        question=question,
                        answer=answer,
                    )
            return None

    async def delete(self, question: str) -> bool:
        """Delete FAQ entry."""
        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)
            return await repo.delete_by_question(question)

    async def search(self, query: str) -> List[dict]:
        """Search FAQ entries."""
        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)
            return await repo.search(query)


# ============== Preset Manager ==============


class AsyncPresetManager:
    """Async TTS preset manager using database."""

    async def get_all(self, owner_id: Optional[int] = None) -> Dict[str, dict]:
        """Get all presets."""
        async with AsyncSessionLocal() as session:
            repo = PresetRepository(session)
            return await repo.get_all_presets(owner_id=owner_id)

    async def get_custom(self) -> Dict[str, dict]:
        """Get only custom presets."""
        async with AsyncSessionLocal() as session:
            repo = PresetRepository(session)
            return await repo.get_custom_presets()

    async def create(self, name: str, params: dict, owner_id: Optional[int] = None) -> dict:
        """Create new preset."""
        async with AsyncSessionLocal() as session:
            repo = PresetRepository(session)
            return await repo.create_preset(name, params, owner_id=owner_id)

    async def update(self, name: str, params: dict) -> Optional[dict]:
        """Update preset."""
        async with AsyncSessionLocal() as session:
            repo = PresetRepository(session)
            return await repo.update_preset(name, params)

    async def delete(self, name: str) -> bool:
        """Delete preset."""
        async with AsyncSessionLocal() as session:
            repo = PresetRepository(session)
            return await repo.delete_preset(name)


# ============== Config Manager ==============


class AsyncConfigManager:
    """Async config manager using database."""

    async def get(self, key: str, default: Any = None) -> Any:
        """Get config value."""
        async with AsyncSessionLocal() as session:
            repo = ConfigRepository(session)
            return await repo.get_config(key, default)

    async def set(self, key: str, value: Any) -> bool:
        """Set config value."""
        async with AsyncSessionLocal() as session:
            repo = ConfigRepository(session)
            return await repo.set_config(key, value)

    async def get_telegram(self) -> dict:
        """Get Telegram config."""
        async with AsyncSessionLocal() as session:
            repo = ConfigRepository(session)
            return await repo.get_telegram_config()

    async def set_telegram(self, config: dict) -> bool:
        """Set Telegram config."""
        async with AsyncSessionLocal() as session:
            repo = ConfigRepository(session)
            return await repo.set_telegram_config(config)

    async def get_widget(self) -> dict:
        """Get widget config."""
        async with AsyncSessionLocal() as session:
            repo = ConfigRepository(session)
            return await repo.get_widget_config()

    async def set_widget(self, config: dict) -> bool:
        """Set widget config."""
        async with AsyncSessionLocal() as session:
            repo = ConfigRepository(session)
            return await repo.set_widget_config(config)


# ============== Telegram Session Manager ==============


class AsyncTelegramSessionManager:
    """Async Telegram session manager using database (supports multi-bot)."""

    async def get_session(self, user_id: int, bot_id: str = "default") -> Optional[str]:
        """Get chat session ID for user in specific bot."""
        async with AsyncSessionLocal() as session:
            repo = TelegramRepository(session, bot_id=bot_id)
            return await repo.get_session(user_id, bot_id=bot_id)

    async def set_session(
        self,
        user_id: int,
        chat_session_id: str,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        bot_id: str = "default",
    ) -> None:
        """Set or update user session for specific bot."""
        async with AsyncSessionLocal() as session:
            repo = TelegramRepository(session, bot_id=bot_id)
            await repo.set_session(
                user_id, chat_session_id, username, first_name, last_name, bot_id=bot_id
            )

    async def get_all_sessions(self, bot_id: Optional[str] = None) -> List[dict]:
        """Get all sessions (optionally for specific bot)."""
        async with AsyncSessionLocal() as session:
            repo = TelegramRepository(session)
            return await repo.get_all_sessions(bot_id=bot_id)

    async def get_sessions_for_bot(self, bot_id: str) -> List[dict]:
        """Get sessions for specific bot instance."""
        async with AsyncSessionLocal() as session:
            repo = TelegramRepository(session, bot_id=bot_id)
            return await repo.get_sessions_for_bot(bot_id)

    async def get_sessions_dict(self, bot_id: str = "default") -> Dict[int, str]:
        """Get sessions as user_id -> session_id dict for specific bot."""
        async with AsyncSessionLocal() as session:
            repo = TelegramRepository(session)
            return await repo.get_sessions_as_dict(bot_id=bot_id)

    async def clear_all(self, bot_id: Optional[str] = None) -> int:
        """Clear all sessions (optionally for specific bot)."""
        async with AsyncSessionLocal() as session:
            repo = TelegramRepository(session)
            return await repo.clear_all_sessions(bot_id=bot_id)

    async def clear_sessions_for_bot(self, bot_id: str) -> int:
        """Clear sessions for specific bot instance."""
        async with AsyncSessionLocal() as session:
            repo = TelegramRepository(session)
            return await repo.clear_sessions_for_bot(bot_id)

    async def get_session_count(self, bot_id: Optional[str] = None) -> int:
        """Get session count (optionally for specific bot)."""
        async with AsyncSessionLocal() as session:
            repo = TelegramRepository(session)
            return await repo.get_session_count(bot_id=bot_id)

    async def get_session_count_by_bot(self) -> Dict[str, int]:
        """Get session counts grouped by bot_id."""
        async with AsyncSessionLocal() as session:
            repo = TelegramRepository(session)
            return await repo.get_session_count_by_bot()


# ============== Bot Instance Manager ==============


class AsyncBotInstanceManager:
    """Async manager for Telegram bot instances."""

    async def list_instances(
        self, enabled_only: bool = False, owner_id: Optional[int] = None
    ) -> List[dict]:
        """List all bot instances."""
        async with AsyncSessionLocal() as session:
            repo = BotInstanceRepository(session)
            return await repo.list_instances(enabled_only=enabled_only, owner_id=owner_id)

    async def get_instance(
        self, instance_id: str, owner_id: Optional[int] = None
    ) -> Optional[dict]:
        """Get bot instance by ID."""
        async with AsyncSessionLocal() as session:
            repo = BotInstanceRepository(session)
            return await repo.get_instance(instance_id, owner_id=owner_id)

    async def get_instance_with_token(self, instance_id: str) -> Optional[dict]:
        """Get bot instance with token (for internal use)."""
        async with AsyncSessionLocal() as session:
            repo = BotInstanceRepository(session)
            return await repo.get_instance_with_token(instance_id)

    async def create_instance(self, name: str, **kwargs: Any) -> dict:
        """Create new bot instance."""
        async with AsyncSessionLocal() as session:
            repo = BotInstanceRepository(session)
            return await repo.create_instance(name, **kwargs)

    async def update_instance(self, instance_id: str, **kwargs: Any) -> Optional[dict]:
        """Update bot instance."""
        async with AsyncSessionLocal() as session:
            repo = BotInstanceRepository(session)
            return await repo.update_instance(instance_id, **kwargs)

    async def delete_instance(self, instance_id: str, owner_id: Optional[int] = None) -> bool:
        """Delete bot instance."""
        async with AsyncSessionLocal() as session:
            repo = BotInstanceRepository(session)
            return await repo.delete_instance(instance_id, owner_id=owner_id)

    async def set_enabled(self, instance_id: str, enabled: bool) -> bool:
        """Enable or disable bot instance."""
        async with AsyncSessionLocal() as session:
            repo = BotInstanceRepository(session)
            return await repo.set_enabled(instance_id, enabled)

    async def set_auto_start(self, instance_id: str, auto_start: bool) -> bool:
        """Set auto-start flag for bot instance."""
        async with AsyncSessionLocal() as session:
            repo = BotInstanceRepository(session)
            return await repo.set_auto_start(instance_id, auto_start)

    async def get_auto_start_instances(self) -> List[dict]:
        """Get all bot instances that should auto-start."""
        async with AsyncSessionLocal() as session:
            repo = BotInstanceRepository(session)
            return await repo.get_auto_start_instances()

    async def get_enabled_instances(self) -> List[dict]:
        """Get all enabled bot instances."""
        async with AsyncSessionLocal() as session:
            repo = BotInstanceRepository(session)
            return await repo.get_enabled_instances()

    async def instance_exists(self, instance_id: str) -> bool:
        """Check if instance exists."""
        async with AsyncSessionLocal() as session:
            repo = BotInstanceRepository(session)
            return await repo.instance_exists(instance_id)

    async def get_instance_count(self) -> int:
        """Get total number of bot instances."""
        async with AsyncSessionLocal() as session:
            repo = BotInstanceRepository(session)
            return await repo.get_instance_count()

    async def import_from_legacy_config(self, config: dict, instance_id: str = "default") -> dict:
        """Import from legacy telegram_config format."""
        async with AsyncSessionLocal() as session:
            repo = BotInstanceRepository(session)
            return await repo.import_from_legacy_config(config, instance_id)


# ============== Widget Instance Manager ==============


class AsyncWidgetInstanceManager:
    """Async manager for website widget instances."""

    async def list_instances(
        self, enabled_only: bool = False, owner_id: Optional[int] = None
    ) -> List[dict]:
        """List all widget instances."""
        async with AsyncSessionLocal() as session:
            repo = WidgetInstanceRepository(session)
            return await repo.list_instances(enabled_only=enabled_only, owner_id=owner_id)

    async def get_instance(
        self, instance_id: str, owner_id: Optional[int] = None
    ) -> Optional[dict]:
        """Get widget instance by ID."""
        async with AsyncSessionLocal() as session:
            repo = WidgetInstanceRepository(session)
            return await repo.get_instance(instance_id, owner_id=owner_id)

    async def create_instance(self, name: str, **kwargs: Any) -> dict:
        """Create new widget instance."""
        async with AsyncSessionLocal() as session:
            repo = WidgetInstanceRepository(session)
            return await repo.create_instance(name, **kwargs)

    async def update_instance(self, instance_id: str, **kwargs: Any) -> Optional[dict]:
        """Update widget instance."""
        async with AsyncSessionLocal() as session:
            repo = WidgetInstanceRepository(session)
            return await repo.update_instance(instance_id, **kwargs)

    async def delete_instance(self, instance_id: str, owner_id: Optional[int] = None) -> bool:
        """Delete widget instance."""
        async with AsyncSessionLocal() as session:
            repo = WidgetInstanceRepository(session)
            return await repo.delete_instance(instance_id, owner_id=owner_id)

    async def set_enabled(self, instance_id: str, enabled: bool) -> bool:
        """Enable or disable widget instance."""
        async with AsyncSessionLocal() as session:
            repo = WidgetInstanceRepository(session)
            return await repo.set_enabled(instance_id, enabled)

    async def get_enabled_instances(self) -> List[dict]:
        """Get all enabled widget instances."""
        async with AsyncSessionLocal() as session:
            repo = WidgetInstanceRepository(session)
            return await repo.get_enabled_instances()

    async def instance_exists(self, instance_id: str) -> bool:
        """Check if instance exists."""
        async with AsyncSessionLocal() as session:
            repo = WidgetInstanceRepository(session)
            return await repo.instance_exists(instance_id)

    async def get_instance_count(self) -> int:
        """Get total number of widget instances."""
        async with AsyncSessionLocal() as session:
            repo = WidgetInstanceRepository(session)
            return await repo.get_instance_count()

    async def import_from_legacy_config(self, config: dict, instance_id: str = "default") -> dict:
        """Import from legacy widget_config format."""
        async with AsyncSessionLocal() as session:
            repo = WidgetInstanceRepository(session)
            return await repo.import_from_legacy_config(config, instance_id)


# ============== Cloud Provider Manager ==============


class AsyncCloudProviderManager:
    """Async manager for cloud LLM providers."""

    async def list_providers(
        self, enabled_only: bool = False, owner_id: Optional[int] = None
    ) -> List[dict]:
        """List all cloud providers."""
        async with AsyncSessionLocal() as session:
            repo = CloudProviderRepository(session)
            return await repo.list_providers(enabled_only=enabled_only, owner_id=owner_id)

    async def get_provider(
        self, provider_id: str, owner_id: Optional[int] = None
    ) -> Optional[dict]:
        """Get provider by ID (without API key)."""
        async with AsyncSessionLocal() as session:
            repo = CloudProviderRepository(session)
            return await repo.get_provider(provider_id, owner_id=owner_id)

    async def get_provider_with_key(self, provider_id: str) -> Optional[dict]:
        """Get provider with API key (for internal use)."""
        async with AsyncSessionLocal() as session:
            repo = CloudProviderRepository(session)
            return await repo.get_provider_with_key(provider_id)

    async def get_default_provider(self) -> Optional[dict]:
        """Get the default cloud provider."""
        async with AsyncSessionLocal() as session:
            repo = CloudProviderRepository(session)
            return await repo.get_default_provider()

    async def get_first_enabled(self) -> Optional[dict]:
        """Get first enabled provider (fallback if no default)."""
        async with AsyncSessionLocal() as session:
            repo = CloudProviderRepository(session)
            return await repo.get_first_enabled()

    async def create_provider(self, name: str, provider_type: str, **kwargs: Any) -> dict:
        """Create new cloud provider."""
        async with AsyncSessionLocal() as session:
            repo = CloudProviderRepository(session)
            return await repo.create_provider(name, provider_type, **kwargs)

    async def update_provider(self, provider_id: str, **kwargs: Any) -> Optional[dict]:
        """Update cloud provider."""
        async with AsyncSessionLocal() as session:
            repo = CloudProviderRepository(session)
            return await repo.update_provider(provider_id, **kwargs)

    async def delete_provider(self, provider_id: str, owner_id: Optional[int] = None) -> bool:
        """Delete cloud provider."""
        async with AsyncSessionLocal() as session:
            repo = CloudProviderRepository(session)
            return await repo.delete_provider(provider_id, owner_id=owner_id)

    async def set_default(self, provider_id: str) -> bool:
        """Set provider as default."""
        async with AsyncSessionLocal() as session:
            repo = CloudProviderRepository(session)
            return await repo.set_default(provider_id)

    async def get_by_type(self, provider_type: str, enabled_only: bool = True) -> List[dict]:
        """Get providers by type."""
        async with AsyncSessionLocal() as session:
            repo = CloudProviderRepository(session)
            return await repo.get_by_type(provider_type, enabled_only)

    async def provider_exists(self, provider_id: str) -> bool:
        """Check if provider exists."""
        async with AsyncSessionLocal() as session:
            repo = CloudProviderRepository(session)
            return await repo.provider_exists(provider_id)

    async def get_provider_count(self) -> int:
        """Get total number of providers."""
        async with AsyncSessionLocal() as session:
            repo = CloudProviderRepository(session)
            return await repo.get_provider_count()


# ============== Audit Logger ==============


class AsyncAuditLogger:
    """Async audit logger using database."""

    async def log(
        self,
        action: str,
        resource: str,
        resource_id: Optional[str] = None,
        user_id: Optional[str] = None,
        user_ip: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        """Log audit event."""
        async with AsyncSessionLocal() as session:
            repo = AuditRepository(session)
            await repo.log(action, resource, resource_id, user_id, user_ip, details)

    async def get_logs(
        self,
        action: Optional[str] = None,
        resource: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        """Get audit logs."""
        async with AsyncSessionLocal() as session:
            repo = AuditRepository(session)
            return await repo.get_logs(action=action, resource=resource, limit=limit)

    async def get_recent(self, hours: int = 24) -> List[dict]:
        """Get recent logs."""
        async with AsyncSessionLocal() as session:
            repo = AuditRepository(session)
            return await repo.get_recent(hours)


# ============== Payment Manager ==============


class AsyncPaymentManager:
    """Async wrapper for PaymentRepository."""

    async def log_payment(self, **kwargs: Any) -> dict:
        """Log a completed payment."""
        async with AsyncSessionLocal() as session:
            repo = PaymentRepository(session)
            return await repo.log_payment(**kwargs)

    async def get_payments_for_bot(self, bot_id: str, limit: int = 100) -> List[dict]:
        """Get payment history for a bot instance."""
        async with AsyncSessionLocal() as session:
            repo = PaymentRepository(session)
            return await repo.get_payments_for_bot(bot_id, limit)

    async def get_payment_stats(self, bot_id: str) -> Dict[str, Any]:
        """Get payment statistics for a bot instance."""
        async with AsyncSessionLocal() as session:
            repo = PaymentRepository(session)
            return await repo.get_payment_stats(bot_id)


# ============== amoCRM Manager ==============


class AsyncAmoCRMManager:
    """Async wrapper for amoCRM config and sync log repositories."""

    async def get_config(self) -> Optional[dict]:
        """Get amoCRM config (secrets masked)."""
        async with AsyncSessionLocal() as session:
            repo = AmoCRMConfigRepository(session)
            return await repo.get_config()

    async def get_config_with_secrets(self) -> Optional[Dict[str, Any]]:
        """Get raw config model for internal use (tokens, secrets)."""
        async with AsyncSessionLocal() as session:
            repo = AmoCRMConfigRepository(session)
            model = await repo.get_config_with_secrets()
            if not model:
                return None
            result = model.to_dict(include_secrets=True)
            result["access_token"] = model.access_token
            result["refresh_token"] = model.refresh_token
            result["token_expires_at"] = (
                model.token_expires_at.isoformat() if model.token_expires_at else None
            )
            return result

    async def save_config(self, **kwargs: Any) -> dict:
        """Create or update amoCRM config."""
        async with AsyncSessionLocal() as session:
            repo = AmoCRMConfigRepository(session)
            return await repo.save_config(**kwargs)

    async def clear_tokens(self) -> dict:
        """Clear OAuth tokens (disconnect)."""
        async with AsyncSessionLocal() as session:
            repo = AmoCRMConfigRepository(session)
            return await repo.clear_tokens()

    async def log_sync(self, **kwargs: Any) -> dict:
        """Log a sync event."""
        async with AsyncSessionLocal() as session:
            repo = AmoCRMSyncLogRepository(session)
            return await repo.log_sync(**kwargs)

    async def get_sync_logs(self, limit: int = 50) -> List[dict]:
        """Get recent sync log entries."""
        async with AsyncSessionLocal() as session:
            repo = AmoCRMSyncLogRepository(session)
            return await repo.get_recent(limit)


# ============== GSM Manager ==============


class AsyncGSMManager:
    """Async wrapper for GSM call and SMS log repositories."""

    async def create_call(
        self,
        direction: str,
        state: str,
        caller_number: str,
        call_id: Optional[str] = None,
    ) -> dict:
        """Create a new call log entry."""
        async with AsyncSessionLocal() as session:
            repo = GSMCallLogRepository(session)
            call = await repo.create_call(direction, state, caller_number, call_id)
            return call.to_dict()

    async def update_call_state(
        self,
        call_id: str,
        state: str,
        answered_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
    ) -> Optional[dict]:
        """Update call state."""
        async with AsyncSessionLocal() as session:
            repo = GSMCallLogRepository(session)
            call = await repo.update_call_state(call_id, state, answered_at, ended_at)
            return call.to_dict() if call else None

    async def get_recent_calls(
        self,
        limit: int = 50,
        offset: int = 0,
        state: Optional[str] = None,
    ) -> List[dict]:
        """Get recent calls."""
        async with AsyncSessionLocal() as session:
            repo = GSMCallLogRepository(session)
            calls = await repo.get_recent_calls(limit, offset, state)
            return [c.to_dict() for c in calls]

    async def count_calls(self, state: Optional[str] = None) -> int:
        """Count calls."""
        async with AsyncSessionLocal() as session:
            repo = GSMCallLogRepository(session)
            return await repo.count_calls(state)

    async def create_sms(
        self,
        direction: str,
        number: str,
        text: str,
        status: str,
    ) -> dict:
        """Create SMS log entry."""
        async with AsyncSessionLocal() as session:
            repo = GSMSMSLogRepository(session)
            sms = await repo.create_sms(direction, number, text, status)
            return sms.to_dict()

    async def get_recent_sms(self, limit: int = 50, offset: int = 0) -> List[dict]:
        """Get recent SMS messages."""
        async with AsyncSessionLocal() as session:
            repo = GSMSMSLogRepository(session)
            messages = await repo.get_recent_sms(limit, offset)
            return [m.to_dict() for m in messages]

    async def count_sms(self) -> int:
        """Count SMS messages."""
        async with AsyncSessionLocal() as session:
            repo = GSMSMSLogRepository(session)
            return await repo.count_sms()


# ============== User Manager ==============


class AsyncUserManager:
    """Async manager for user authentication and CRUD."""

    async def authenticate(self, username: str, password: str) -> Optional[dict]:
        """Authenticate user. Returns user dict or None."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            return await repo.authenticate(username, password)

    async def get_by_username(self, username: str) -> Optional[dict]:
        """Get user by username."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            user = await repo.get_by_username(username)
            return user.to_dict() if user else None

    async def get_by_id(self, user_id: int) -> Optional[dict]:
        """Get user by ID."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            user = await repo.get_by_id(user_id)
            return user.to_dict() if user else None

    async def create_user(
        self,
        username: str,
        password: str,
        role: str = "user",
        display_name: Optional[str] = None,
    ) -> dict:
        """Create a new user."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            return await repo.create_user(username, password, role, display_name)

    async def update_password(self, user_id: int, new_password: str) -> bool:
        """Update user password."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            return await repo.update_password(user_id, new_password)

    async def update_profile(
        self, user_id: int, display_name: Optional[str] = None
    ) -> Optional[dict]:
        """Update user profile."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            return await repo.update_profile(user_id, display_name)

    async def set_role(self, user_id: int, role: str) -> bool:
        """Change user role."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            return await repo.set_role(user_id, role)

    async def set_active(self, user_id: int, active: bool) -> bool:
        """Enable or disable user."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            return await repo.set_active(user_id, active)

    async def list_users(self, include_inactive: bool = False) -> List[dict]:
        """List all users."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            return await repo.list_users(include_inactive)

    async def delete_user(self, user_id: int) -> bool:
        """Delete user."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            return await repo.delete_user(user_id)

    async def get_user_count(self) -> int:
        """Get active user count."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            return await repo.get_user_count()


# ============== Knowledge Document Manager ==============


class AsyncKnowledgeDocManager:
    """Async wrapper for KnowledgeDocumentRepository."""

    async def get_all(self) -> List[dict]:
        """Get all knowledge documents."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeDocumentRepository(session)
            return await repo.get_all_documents()

    async def get_by_id(self, doc_id: int) -> Optional[dict]:
        """Get document by ID."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeDocumentRepository(session)
            doc = await repo.get_by_id(doc_id)
            return doc.to_dict() if doc else None

    async def get_by_filename(self, filename: str) -> Optional[dict]:
        """Get document by filename."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeDocumentRepository(session)
            doc = await repo.get_by_filename(filename)
            return doc.to_dict() if doc else None

    async def create(
        self,
        filename: str,
        title: str,
        source_type: str = "manual",
        file_size_bytes: int = 0,
        section_count: int = 0,
        owner_id: Optional[int] = None,
    ) -> dict:
        """Create a knowledge document record."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeDocumentRepository(session)
            return await repo.create_document(
                filename=filename,
                title=title,
                source_type=source_type,
                file_size_bytes=file_size_bytes,
                section_count=section_count,
                owner_id=owner_id,
            )

    async def update(
        self,
        doc_id: int,
        title: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        section_count: Optional[int] = None,
    ) -> Optional[dict]:
        """Update document metadata."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeDocumentRepository(session)
            return await repo.update_document(doc_id, title, file_size_bytes, section_count)

    async def delete(self, doc_id: int) -> bool:
        """Delete document record."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeDocumentRepository(session)
            return await repo.delete_document(doc_id)


# ============== Global Instances ==============

# These can be used directly in orchestrator
async_chat_manager = AsyncChatManager()
async_faq_manager = AsyncFAQManager()
async_preset_manager = AsyncPresetManager()
async_config_manager = AsyncConfigManager()
async_telegram_manager = AsyncTelegramSessionManager()
async_audit_logger = AsyncAuditLogger()
async_bot_instance_manager = AsyncBotInstanceManager()
async_widget_instance_manager = AsyncWidgetInstanceManager()
async_cloud_provider_manager = AsyncCloudProviderManager()
async_payment_manager = AsyncPaymentManager()
async_amocrm_manager = AsyncAmoCRMManager()
async_gsm_manager = AsyncGSMManager()
async_user_manager = AsyncUserManager()
async_knowledge_doc_manager = AsyncKnowledgeDocManager()


# ============== Initialization Function ==============


async def init_database() -> None:
    """Initialize database - call this on startup."""
    await db_manager.initialize()


async def shutdown_database() -> None:
    """Shutdown database - call this on shutdown."""
    await db_manager.shutdown()


async def get_database_status() -> dict:
    """Get database status for health checks."""
    return await db_manager.get_status()
