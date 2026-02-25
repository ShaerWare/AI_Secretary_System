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
    ChatShareRepository,
    ClaudeCodeRepository,
    CloudProviderRepository,
    ConfigRepository,
    FAQRepository,
    GSMCallLogRepository,
    GSMSMSLogRepository,
    KanbanProjectRepository,
    KanbanRepository,
    KnowledgeCollectionRepository,
    KnowledgeDocumentRepository,
    PaymentRepository,
    PresetRepository,
    RoleRepository,
    TelegramRepository,
    UserIdentityRepository,
    UserRepository,
    UserSessionRepository,
    WhatsAppInstanceRepository,
    WidgetInstanceRepository,
    WooCommerceConfigRepository,
    WorkspaceRepository,
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

    async def list_sessions(
        self,
        owner_id: Optional[int] = None,
        source: Optional[str] = None,
        exclude_source: Optional[str] = None,
        workspace_id: Optional[int] = None,
    ) -> List[dict]:
        """List all sessions with summary info."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.list_sessions(
                owner_id=owner_id,
                source=source,
                exclude_source=exclude_source,
                workspace_id=workspace_id,
            )

    async def get_session(
        self,
        session_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> Optional[dict]:
        """Get full session with messages."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.get_session(session_id, owner_id=owner_id, workspace_id=workspace_id)

    async def create_session(
        self,
        title: Optional[str] = None,
        system_prompt: Optional[str] = None,
        source: Optional[str] = None,
        source_id: Optional[str] = None,
        owner_id: Optional[int] = None,
        rag_mode: Optional[str] = None,
        knowledge_collection_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> dict:
        """Create new session."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.create_session(
                title,
                system_prompt,
                source,
                source_id,
                owner_id=owner_id,
                rag_mode=rag_mode,
                knowledge_collection_id=knowledge_collection_id,
                workspace_id=workspace_id,
            )

    async def update_session(
        self,
        session_id: str,
        title: Optional[str] = None,
        system_prompt: Optional[str] = None,
        pinned: Optional[bool] = None,
        rag_mode: Optional[str] = None,
        knowledge_collection_id: Optional[int] = None,
        knowledge_collection_ids: Optional[list[int]] = None,
        context_files: Optional[list] = None,
    ) -> Optional[dict]:
        """Update session title, system prompt, pinned status, RAG config, or context files."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.update_session(
                session_id,
                title,
                system_prompt,
                pinned=pinned,
                rag_mode=rag_mode,
                knowledge_collection_id=knowledge_collection_id,
                knowledge_collection_ids=knowledge_collection_ids,
                context_files=context_files,
            )

    async def delete_session(
        self,
        session_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> bool:
        """Delete session."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.delete_session(
                session_id, owner_id=owner_id, workspace_id=workspace_id
            )

    async def delete_sessions_bulk(
        self,
        session_ids: List[str],
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> int:
        """Delete multiple sessions by ID list."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.delete_sessions_bulk(
                session_ids, owner_id=owner_id, workspace_id=workspace_id
            )

    async def list_sessions_grouped(
        self, owner_id: Optional[int] = None, workspace_id: Optional[int] = None
    ) -> dict:
        """Get sessions grouped by source."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.list_sessions_grouped(owner_id=owner_id, workspace_id=workspace_id)

    async def get_branch_path(self, session_id: str, message_id: str) -> List[dict]:
        """Get ordered message path from root to a specific message."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.get_branch_path(session_id, message_id)

    async def get_active_messages(self, session_id: str) -> List[dict]:
        """Get active (visible) messages for a session."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.get_active_messages(session_id)

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        parent_id: Optional[str] = None,
    ) -> Optional[dict]:
        """Add message to session."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.add_message(session_id, role, content, parent_id=parent_id)

    async def edit_message(
        self,
        session_id: str,
        message_id: str,
        content: str,
    ) -> Optional[dict]:
        """Non-destructive edit: creates new sibling branch."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.edit_message(session_id, message_id, content)

    async def branch_regenerate(
        self,
        session_id: str,
        message_id: str,
    ) -> Optional[dict]:
        """Non-destructive regenerate: deactivate and return parent user msg."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.branch_regenerate(session_id, message_id)

    async def delete_message(
        self,
        session_id: str,
        message_id: str,
    ) -> bool:
        """Delete message and all subsequent messages."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.delete_message(session_id, message_id)

    async def get_branch_tree(
        self, session_id: str, visible_ids: Optional[set[str]] = None
    ) -> List[dict]:
        """Get branch tree structure for a session."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.get_branch_tree(session_id, visible_ids=visible_ids)

    async def compute_branch_visible_ids(self, session_id: str, branch_message_id: str) -> set[str]:
        """Compute visible message IDs for a shared branch."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.compute_branch_visible_ids(session_id, branch_message_id)

    async def get_sibling_info(self, session_id: str) -> dict:
        """Get sibling info for messages with alternatives."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.get_sibling_info(session_id)

    async def switch_branch(self, session_id: str, message_id: str) -> bool:
        """Switch active branch to the given message."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.switch_branch(session_id, message_id)

    async def start_new_branch(self, session_id: str) -> bool:
        """Deactivate all active messages to start a fresh branch."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.start_new_branch(session_id)

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

    async def get_all(self, workspace_id: Optional[int] = None) -> Dict[str, str]:
        """Get all FAQ as question->answer dict."""
        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)
            return await repo.get_as_dict(workspace_id=workspace_id)

    async def get_all_entries(self, workspace_id: Optional[int] = None) -> List[dict]:
        """Get all FAQ entries with full details."""
        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)
            return await repo.get_all_entries(enabled_only=False, workspace_id=workspace_id)

    async def find_answer(self, question: str) -> Optional[str]:
        """Find exact match answer for question."""
        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)
            return await repo.find_answer(question)

    async def add(self, question: str, answer: str, workspace_id: Optional[int] = None) -> dict:
        """Add new FAQ entry."""
        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)
            return await repo.create_entry(question, answer, workspace_id=workspace_id)

    async def update(
        self,
        old_question: str,
        question: str,
        answer: str,
        workspace_id: Optional[int] = None,
    ) -> Optional[dict]:
        """Update FAQ entry."""
        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)

            # If question changed, need to find by old and delete + create
            if old_question != question:
                existing = await repo.get_by_question(old_question)
                if existing:
                    await repo.delete_by_question(old_question)
                return await repo.create_entry(question, answer, workspace_id=workspace_id)
            else:
                existing = await repo.get_by_question(question)
                if existing:
                    return await repo.update_entry(
                        existing["id"],
                        question=question,
                        answer=answer,
                    )
            return None

    async def delete(self, question: str, workspace_id: Optional[int] = None) -> bool:
        """Delete FAQ entry."""
        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)
            return await repo.delete_by_question(question, workspace_id=workspace_id)

    async def search(self, query: str, workspace_id: Optional[int] = None) -> List[dict]:
        """Search FAQ entries."""
        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)
            return await repo.search(query, workspace_id=workspace_id)


# ============== Preset Manager ==============


class AsyncPresetManager:
    """Async TTS preset manager using database."""

    async def get_all(
        self, owner_id: Optional[int] = None, workspace_id: Optional[int] = None
    ) -> Dict[str, dict]:
        """Get all presets."""
        async with AsyncSessionLocal() as session:
            repo = PresetRepository(session)
            return await repo.get_all_presets(owner_id=owner_id, workspace_id=workspace_id)

    async def get_custom(
        self, owner_id: Optional[int] = None, workspace_id: Optional[int] = None
    ) -> Dict[str, dict]:
        """Get only custom presets."""
        async with AsyncSessionLocal() as session:
            repo = PresetRepository(session)
            return await repo.get_custom_presets(owner_id=owner_id, workspace_id=workspace_id)

    async def create(
        self,
        name: str,
        params: dict,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> dict:
        """Create new preset."""
        async with AsyncSessionLocal() as session:
            repo = PresetRepository(session)
            return await repo.create_preset(
                name, params, owner_id=owner_id, workspace_id=workspace_id
            )

    async def update(
        self, name: str, params: dict, workspace_id: Optional[int] = None
    ) -> Optional[dict]:
        """Update preset."""
        async with AsyncSessionLocal() as session:
            repo = PresetRepository(session)
            return await repo.update_preset(name, params, workspace_id=workspace_id)

    async def delete(self, name: str, workspace_id: Optional[int] = None) -> bool:
        """Delete preset."""
        async with AsyncSessionLocal() as session:
            repo = PresetRepository(session)
            return await repo.delete_preset(name, workspace_id=workspace_id)


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

            # Track Telegram contact as user identity
            try:
                identity_repo = UserIdentityRepository(session)
                display = first_name or username or str(user_id)
                await identity_repo.find_or_create(
                    provider="telegram",
                    provider_uid=str(user_id),
                    display_name=display,
                    metadata_dict={
                        "username": username,
                        "first_name": first_name,
                        "last_name": last_name,
                    },
                )
            except Exception:
                logger.debug("Failed to track Telegram identity for %s", user_id, exc_info=True)

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
        self,
        enabled_only: bool = False,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> List[dict]:
        """List all bot instances."""
        async with AsyncSessionLocal() as session:
            repo = BotInstanceRepository(session)
            return await repo.list_instances(
                enabled_only=enabled_only, owner_id=owner_id, workspace_id=workspace_id
            )

    async def get_instance(
        self,
        instance_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> Optional[dict]:
        """Get bot instance by ID."""
        async with AsyncSessionLocal() as session:
            repo = BotInstanceRepository(session)
            return await repo.get_instance(
                instance_id, owner_id=owner_id, workspace_id=workspace_id
            )

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

    async def delete_instance(
        self,
        instance_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> bool:
        """Delete bot instance."""
        async with AsyncSessionLocal() as session:
            repo = BotInstanceRepository(session)
            return await repo.delete_instance(
                instance_id, owner_id=owner_id, workspace_id=workspace_id
            )

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
        self,
        enabled_only: bool = False,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> List[dict]:
        """List all widget instances."""
        async with AsyncSessionLocal() as session:
            repo = WidgetInstanceRepository(session)
            return await repo.list_instances(
                enabled_only=enabled_only, owner_id=owner_id, workspace_id=workspace_id
            )

    async def get_instance(
        self,
        instance_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> Optional[dict]:
        """Get widget instance by ID."""
        async with AsyncSessionLocal() as session:
            repo = WidgetInstanceRepository(session)
            return await repo.get_instance(
                instance_id, owner_id=owner_id, workspace_id=workspace_id
            )

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

    async def delete_instance(
        self,
        instance_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> bool:
        """Delete widget instance."""
        async with AsyncSessionLocal() as session:
            repo = WidgetInstanceRepository(session)
            return await repo.delete_instance(
                instance_id, owner_id=owner_id, workspace_id=workspace_id
            )

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


# ============== WhatsApp Instance Manager ==============


class AsyncWhatsAppInstanceManager:
    """Async manager for WhatsApp bot instances."""

    async def list_instances(
        self,
        enabled_only: bool = False,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> List[dict]:
        """List all WhatsApp instances."""
        async with AsyncSessionLocal() as session:
            repo = WhatsAppInstanceRepository(session)
            return await repo.list_instances(
                enabled_only=enabled_only, owner_id=owner_id, workspace_id=workspace_id
            )

    async def get_instance(
        self,
        instance_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> Optional[dict]:
        """Get WhatsApp instance by ID."""
        async with AsyncSessionLocal() as session:
            repo = WhatsAppInstanceRepository(session)
            return await repo.get_instance(
                instance_id, owner_id=owner_id, workspace_id=workspace_id
            )

    async def get_instance_with_token(self, instance_id: str) -> Optional[dict]:
        """Get WhatsApp instance with token (for internal use)."""
        async with AsyncSessionLocal() as session:
            repo = WhatsAppInstanceRepository(session)
            return await repo.get_instance_with_token(instance_id)

    async def create_instance(self, name: str, **kwargs: Any) -> dict:
        """Create new WhatsApp instance."""
        async with AsyncSessionLocal() as session:
            repo = WhatsAppInstanceRepository(session)
            return await repo.create_instance(name, **kwargs)

    async def update_instance(self, instance_id: str, **kwargs: Any) -> Optional[dict]:
        """Update WhatsApp instance."""
        async with AsyncSessionLocal() as session:
            repo = WhatsAppInstanceRepository(session)
            return await repo.update_instance(instance_id, **kwargs)

    async def delete_instance(
        self,
        instance_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> bool:
        """Delete WhatsApp instance."""
        async with AsyncSessionLocal() as session:
            repo = WhatsAppInstanceRepository(session)
            return await repo.delete_instance(
                instance_id, owner_id=owner_id, workspace_id=workspace_id
            )

    async def set_enabled(self, instance_id: str, enabled: bool) -> bool:
        """Enable or disable WhatsApp instance."""
        async with AsyncSessionLocal() as session:
            repo = WhatsAppInstanceRepository(session)
            return await repo.set_enabled(instance_id, enabled)

    async def set_auto_start(self, instance_id: str, auto_start: bool) -> bool:
        """Set auto-start flag for WhatsApp instance."""
        async with AsyncSessionLocal() as session:
            repo = WhatsAppInstanceRepository(session)
            return await repo.set_auto_start(instance_id, auto_start)

    async def get_auto_start_instances(self) -> List[dict]:
        """Get all WhatsApp instances that should auto-start."""
        async with AsyncSessionLocal() as session:
            repo = WhatsAppInstanceRepository(session)
            return await repo.get_auto_start_instances()

    async def get_enabled_instances(self) -> List[dict]:
        """Get all enabled WhatsApp instances."""
        async with AsyncSessionLocal() as session:
            repo = WhatsAppInstanceRepository(session)
            return await repo.get_enabled_instances()

    async def instance_exists(self, instance_id: str) -> bool:
        """Check if instance exists."""
        async with AsyncSessionLocal() as session:
            repo = WhatsAppInstanceRepository(session)
            return await repo.instance_exists(instance_id)

    async def get_instance_count(self) -> int:
        """Get total number of WhatsApp instances."""
        async with AsyncSessionLocal() as session:
            repo = WhatsAppInstanceRepository(session)
            return await repo.get_instance_count()


# ============== Cloud Provider Manager ==============


class AsyncCloudProviderManager:
    """Async manager for cloud LLM providers."""

    async def list_providers(
        self,
        enabled_only: bool = False,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> List[dict]:
        """List all cloud providers."""
        async with AsyncSessionLocal() as session:
            repo = CloudProviderRepository(session)
            return await repo.list_providers(
                enabled_only=enabled_only, owner_id=owner_id, workspace_id=workspace_id
            )

    async def get_provider(
        self,
        provider_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> Optional[dict]:
        """Get provider by ID (without API key)."""
        async with AsyncSessionLocal() as session:
            repo = CloudProviderRepository(session)
            return await repo.get_provider(
                provider_id, owner_id=owner_id, workspace_id=workspace_id
            )

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

    async def delete_provider(
        self,
        provider_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> bool:
        """Delete cloud provider."""
        async with AsyncSessionLocal() as session:
            repo = CloudProviderRepository(session)
            return await repo.delete_provider(
                provider_id, owner_id=owner_id, workspace_id=workspace_id
            )

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

    async def get_config(self, workspace_id: Optional[int] = None) -> Optional[dict]:
        """Get amoCRM config (secrets masked)."""
        async with AsyncSessionLocal() as session:
            repo = AmoCRMConfigRepository(session)
            return await repo.get_config(workspace_id=workspace_id)

    async def get_config_with_secrets(
        self, workspace_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Get raw config model for internal use (tokens, secrets)."""
        async with AsyncSessionLocal() as session:
            repo = AmoCRMConfigRepository(session)
            model = await repo.get_config_with_secrets(workspace_id=workspace_id)
            if not model:
                return None
            result = model.to_dict(include_secrets=True)
            result["access_token"] = model.access_token
            result["refresh_token"] = model.refresh_token
            result["token_expires_at"] = (
                model.token_expires_at.isoformat() if model.token_expires_at else None
            )
            return result

    async def save_config(self, workspace_id: Optional[int] = None, **kwargs: Any) -> dict:
        """Create or update amoCRM config."""
        async with AsyncSessionLocal() as session:
            repo = AmoCRMConfigRepository(session)
            return await repo.save_config(workspace_id=workspace_id, **kwargs)

    async def clear_tokens(self, workspace_id: Optional[int] = None) -> dict:
        """Clear OAuth tokens (disconnect)."""
        async with AsyncSessionLocal() as session:
            repo = AmoCRMConfigRepository(session)
            return await repo.clear_tokens(workspace_id=workspace_id)

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


# ============== WooCommerce Manager ==============


class AsyncWooCommerceManager:
    """Async wrapper for WooCommerce config repository."""

    async def get_config(self) -> Optional[dict]:
        """Get WooCommerce config (secrets masked)."""
        async with AsyncSessionLocal() as session:
            repo = WooCommerceConfigRepository(session)
            return await repo.get_config()

    async def get_config_with_secrets(self) -> Optional[Dict[str, Any]]:
        """Get raw config for internal use (credentials)."""
        async with AsyncSessionLocal() as session:
            repo = WooCommerceConfigRepository(session)
            model = await repo.get_config_with_secrets()
            if not model:
                return None
            return model.to_dict(include_secrets=True)

    async def save_config(self, **kwargs: Any) -> dict:
        """Create or update WooCommerce config."""
        async with AsyncSessionLocal() as session:
            repo = WooCommerceConfigRepository(session)
            return await repo.save_config(**kwargs)

    async def clear_credentials(self) -> dict:
        """Clear store credentials (disconnect)."""
        async with AsyncSessionLocal() as session:
            repo = WooCommerceConfigRepository(session)
            return await repo.clear_credentials()


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


# ============== User Session Manager ==============


class AsyncUserSessionManager:
    """Async manager for user session tracking and revocation."""

    async def create_session(
        self,
        user_id: int,
        jti: str,
        ip_address: Optional[str],
        user_agent: Optional[str],
        expires_at: "datetime",
        workspace_id: Optional[int] = None,
    ) -> dict:
        """Create a new session record."""
        async with AsyncSessionLocal() as session:
            repo = UserSessionRepository(session)
            return await repo.create_session(
                user_id,
                jti,
                ip_address,
                user_agent,
                expires_at,
                workspace_id=workspace_id,
            )

    async def get_by_jti(self, jti: str):
        """Get session by JTI with user join."""
        async with AsyncSessionLocal() as session:
            repo = UserSessionRepository(session)
            return await repo.get_by_jti(jti)

    async def get_active_for_user(self, user_id: int) -> List[dict]:
        """Get active sessions for a user."""
        async with AsyncSessionLocal() as session:
            repo = UserSessionRepository(session)
            return await repo.get_active_for_user(user_id)

    async def revoke_by_jti(self, jti: str) -> bool:
        """Revoke a single session."""
        async with AsyncSessionLocal() as session:
            repo = UserSessionRepository(session)
            return await repo.revoke_by_jti(jti)

    async def revoke_all_for_user(self, user_id: int) -> int:
        """Revoke all sessions for a user."""
        async with AsyncSessionLocal() as session:
            repo = UserSessionRepository(session)
            return await repo.revoke_all_for_user(user_id)

    async def cleanup_expired(self, days: int = 7) -> int:
        """Delete old expired sessions."""
        async with AsyncSessionLocal() as session:
            repo = UserSessionRepository(session)
            return await repo.cleanup_expired(days)


async_session_manager = AsyncUserSessionManager()


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
        """Update user password. Revokes all existing sessions."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            result = await repo.update_password(user_id, new_password)
        if result:
            await self._revoke_user_sessions(user_id)
        return result

    async def update_profile(
        self, user_id: int, display_name: Optional[str] = None
    ) -> Optional[dict]:
        """Update user profile."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            return await repo.update_profile(user_id, display_name)

    async def set_role(self, user_id: int, role: str) -> bool:
        """Change user role. Revokes all existing sessions."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            result = await repo.set_role(user_id, role)
        if result:
            await self._revoke_user_sessions(user_id)
        return result

    async def set_active(self, user_id: int, active: bool) -> bool:
        """Enable or disable user. Revokes sessions on deactivation."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            result = await repo.set_active(user_id, active)
        if result and not active:
            await self._revoke_user_sessions(user_id)
        return result

    async def _revoke_user_sessions(self, user_id: int) -> None:
        """Revoke all sessions and clear cache for a user."""
        from auth_manager import revoke_all_user_sessions

        try:
            await revoke_all_user_sessions(user_id)
        except Exception as e:
            logger.warning(f"Failed to revoke sessions for user {user_id}: {e}")

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

    async def get_all(self, workspace_id: Optional[int] = None) -> List[dict]:
        """Get all knowledge documents."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeDocumentRepository(session)
            return await repo.get_all_documents(workspace_id=workspace_id)

    async def get_by_id(self, doc_id: int, workspace_id: Optional[int] = None) -> Optional[dict]:
        """Get document by ID, with optional workspace gate-check."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeDocumentRepository(session)
            doc = await repo.get_by_id_ws(doc_id, workspace_id)
            return doc.to_dict() if doc else None

    async def get_by_filename(self, filename: str) -> Optional[dict]:
        """Get document by filename."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeDocumentRepository(session)
            doc = await repo.get_by_filename(filename)
            return doc.to_dict() if doc else None

    async def get_by_collection(
        self, collection_id: int, workspace_id: Optional[int] = None
    ) -> List[dict]:
        """Get all documents in a specific collection."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeDocumentRepository(session)
            return await repo.get_by_collection(collection_id, workspace_id=workspace_id)

    async def create(
        self,
        filename: str,
        title: str,
        source_type: str = "manual",
        file_size_bytes: int = 0,
        section_count: int = 0,
        owner_id: Optional[int] = None,
        collection_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
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
                collection_id=collection_id,
                workspace_id=workspace_id,
            )

    async def update(
        self,
        doc_id: int,
        title: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        section_count: Optional[int] = None,
        collection_id: Optional[int] = None,
    ) -> Optional[dict]:
        """Update document metadata."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeDocumentRepository(session)
            return await repo.update_document(
                doc_id, title, file_size_bytes, section_count, collection_id
            )

    async def delete(self, doc_id: int) -> bool:
        """Delete document record."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeDocumentRepository(session)
            return await repo.delete_document(doc_id)


# ============== Knowledge Collection Manager ==============


class AsyncKnowledgeCollectionManager:
    """Async wrapper for KnowledgeCollectionRepository."""

    async def get_all(
        self, enabled_only: bool = False, workspace_id: Optional[int] = None
    ) -> List[dict]:
        """Get all collections."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeCollectionRepository(session)
            return await repo.get_all_collections(
                enabled_only=enabled_only, workspace_id=workspace_id
            )

    async def get_by_id(
        self, collection_id: int, workspace_id: Optional[int] = None
    ) -> Optional[dict]:
        """Get collection by ID with document count and optional workspace gate-check."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeCollectionRepository(session)
            col = await repo.get_by_id_ws(collection_id, workspace_id)
            if not col:
                return None
            d = col.to_dict()
            # Add document count
            from sqlalchemy import func
            from sqlalchemy import select as sa_select

            from db.models import KnowledgeDocument

            result = await session.execute(
                sa_select(func.count())
                .select_from(KnowledgeDocument)
                .where(KnowledgeDocument.collection_id == collection_id)
            )
            d["document_count"] = result.scalar() or 0
            return d

    async def get_by_slug(self, slug: str) -> Optional[dict]:
        """Get collection by slug with document count."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeCollectionRepository(session)
            col = await repo.get_by_slug(slug)
            if not col:
                return None
            d = col.to_dict()
            from sqlalchemy import func
            from sqlalchemy import select as sa_select

            from db.models import KnowledgeDocument

            result = await session.execute(
                sa_select(func.count())
                .select_from(KnowledgeDocument)
                .where(KnowledgeDocument.collection_id == col.id)
            )
            d["document_count"] = result.scalar() or 0
            return d

    async def get_default(self) -> Optional[dict]:
        """Get the default collection."""
        return await self.get_by_slug("default")

    async def create(
        self,
        name: str,
        slug: str,
        description: Optional[str] = None,
        enabled: bool = True,
        base_dir: str = "wiki-pages",
        workspace_id: Optional[int] = None,
    ) -> dict:
        """Create a collection."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeCollectionRepository(session)
            return await repo.create_collection(
                name=name,
                slug=slug,
                description=description,
                enabled=enabled,
                base_dir=base_dir,
                workspace_id=workspace_id,
            )

    async def update(
        self,
        collection_id: int,
        name: Optional[str] = None,
        slug: Optional[str] = None,
        description: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[dict]:
        """Update collection metadata."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeCollectionRepository(session)
            return await repo.update_collection(collection_id, name, slug, description, enabled)

    async def delete(self, collection_id: int) -> bool:
        """Delete collection (orphans documents)."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeCollectionRepository(session)
            return await repo.delete_collection(collection_id)

    async def get_document_filenames(self, collection_id: int) -> List[str]:
        """Get filenames of all documents in a collection."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeCollectionRepository(session)
            return await repo.get_document_filenames(collection_id)

    async def ensure_default_exists(self) -> dict:
        """Create default collection if it doesn't exist."""
        default = await self.get_default()
        if default:
            return default
        return await self.create(
            name="Default",
            slug="default",
            description="Коллекция по умолчанию",
            enabled=True,
        )


# ============== Chat Share Manager ==============


class AsyncChatShareManager:
    """Async manager for chat session sharing between users."""

    async def get_shares(self, session_id: str) -> List[dict]:
        """Get all shares for a session with user info."""
        async with AsyncSessionLocal() as session:
            repo = ChatShareRepository(session)
            return await repo.get_shares_for_session(session_id)

    async def add_share(
        self,
        session_id: str,
        user_id: int,
        permission: str = "read",
        shared_by: Optional[int] = None,
        branch_message_id: Optional[str] = None,
    ) -> dict:
        """Add or update a share."""
        async with AsyncSessionLocal() as session:
            repo = ChatShareRepository(session)
            return await repo.add_share(
                session_id, user_id, permission, shared_by, branch_message_id
            )

    async def get_user_share(self, session_id: str, user_id: int) -> Optional[dict]:
        """Get full share record for a user (with branch_message_id)."""
        async with AsyncSessionLocal() as session:
            repo = ChatShareRepository(session)
            share = await repo.get_share(session_id, user_id)
            return share.to_dict() if share else None

    async def remove_share(self, session_id: str, user_id: int) -> bool:
        """Remove a share."""
        async with AsyncSessionLocal() as session:
            repo = ChatShareRepository(session)
            return await repo.remove_share(session_id, user_id)

    async def update_permission(self, session_id: str, user_id: int, permission: str) -> bool:
        """Update share permission."""
        async with AsyncSessionLocal() as session:
            repo = ChatShareRepository(session)
            return await repo.update_permission(session_id, user_id, permission)

    async def get_user_permission(self, session_id: str, user_id: int) -> Optional[str]:
        """Get user's permission for a session."""
        async with AsyncSessionLocal() as session:
            repo = ChatShareRepository(session)
            return await repo.get_user_permission(session_id, user_id)

    async def get_share_counts(self, session_ids: list[str]) -> dict[str, int]:
        """Get share counts for multiple sessions in a single query."""
        async with AsyncSessionLocal() as session:
            repo = ChatShareRepository(session)
            return await repo.get_share_counts(session_ids)

    async def get_shared_sessions_with_permissions(self, user_id: int) -> Dict[str, str]:
        """Get dict of session_id -> permission for all sessions shared with user."""
        async with AsyncSessionLocal() as session:
            repo = ChatShareRepository(session)
            return await repo.get_shared_sessions_with_permissions(user_id)

    async def fork_session(
        self,
        session_id: str,
        new_owner_id: int,
        new_title: Optional[str] = None,
    ) -> Optional[dict]:
        """Fork (deep copy) a session to a new owner."""
        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)
            return await repo.fork_session(session_id, new_owner_id, new_title)

    async def list_shareable_users(self, exclude_user_id: Optional[int] = None) -> List[dict]:
        """Get list of active non-guest users for sharing."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            users = await repo.list_users()
            return [
                {
                    "id": u["id"],
                    "username": u["username"],
                    "display_name": u["display_name"],
                    "role": u["role"],
                }
                for u in users
                if u.get("is_active", True)
                and u.get("role") != "guest"
                and u["id"] != exclude_user_id
            ]


# ============== Claude Code Manager ==============


class AsyncClaudeCodeManager:
    """Manager for Claude Code session CRUD."""

    async def list_sessions(
        self,
        owner_id: Optional[int] = None,
        limit: int = 50,
        workspace_id: Optional[int] = None,
    ) -> List[dict]:
        async with AsyncSessionLocal() as session:
            repo = ClaudeCodeRepository(session)
            return await repo.list_sessions(
                owner_id=owner_id, limit=limit, workspace_id=workspace_id
            )

    async def get_session(
        self, session_id: str, workspace_id: Optional[int] = None
    ) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = ClaudeCodeRepository(session)
            return await repo.get_session(session_id, workspace_id=workspace_id)

    async def create_session(
        self,
        title: str,
        owner_id: int,
        working_directory: str = "/opt/ai-secretary",
        workspace_id: Optional[int] = None,
    ) -> dict:
        async with AsyncSessionLocal() as session:
            repo = ClaudeCodeRepository(session)
            return await repo.create_session(
                title, owner_id, working_directory, workspace_id=workspace_id
            )

    async def update_session(self, session_id: str, **kwargs) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = ClaudeCodeRepository(session)
            return await repo.update_session(session_id, **kwargs)

    async def delete_session(self, session_id: str, workspace_id: Optional[int] = None) -> bool:
        async with AsyncSessionLocal() as session:
            repo = ClaudeCodeRepository(session)
            return await repo.delete_session(session_id, workspace_id=workspace_id)


# ============== User Identity Manager ==============


class AsyncUserIdentityManager:
    """Async manager for external user identities (Telegram, WhatsApp, Widget)."""

    async def find_or_create(
        self,
        provider: str,
        provider_uid: str,
        display_name: Optional[str] = None,
        metadata_dict: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """Find existing identity or create contact user + identity."""
        async with AsyncSessionLocal() as session:
            repo = UserIdentityRepository(session)
            return await repo.find_or_create(provider, provider_uid, display_name, metadata_dict)

    async def get_identities_for_user(self, user_id: int) -> List[dict]:
        """Get all identities linked to a user."""
        async with AsyncSessionLocal() as session:
            repo = UserIdentityRepository(session)
            return await repo.get_identities_for_user(user_id)

    async def link_identity(
        self,
        user_id: int,
        provider: str,
        provider_uid: str,
        display_name: Optional[str] = None,
        metadata_dict: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """Link an external identity to an existing user."""
        async with AsyncSessionLocal() as session:
            repo = UserIdentityRepository(session)
            return await repo.link_identity(
                user_id, provider, provider_uid, display_name, metadata_dict
            )

    async def update_last_seen(self, provider: str, provider_uid: str) -> bool:
        """Touch the last_seen timestamp for an identity."""
        async with AsyncSessionLocal() as session:
            repo = UserIdentityRepository(session)
            return await repo.update_last_seen(provider, provider_uid)


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
async_whatsapp_instance_manager = AsyncWhatsAppInstanceManager()
async_cloud_provider_manager = AsyncCloudProviderManager()
async_payment_manager = AsyncPaymentManager()
async_amocrm_manager = AsyncAmoCRMManager()
async_woocommerce_manager = AsyncWooCommerceManager()
async_gsm_manager = AsyncGSMManager()
async_user_manager = AsyncUserManager()
async_user_identity_manager = AsyncUserIdentityManager()
async_knowledge_doc_manager = AsyncKnowledgeDocManager()
async_knowledge_collection_manager = AsyncKnowledgeCollectionManager()
async_chat_share_manager = AsyncChatShareManager()
async_claude_code_manager = AsyncClaudeCodeManager()


# ============== Kanban Manager ==============


class AsyncKanbanManager:
    """Async kanban task manager."""

    async def get_visible_tasks(
        self,
        current_user_id: int,
        is_admin: bool,
        workspace_id: Optional[int] = None,
    ) -> list:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            return await repo.get_visible_tasks(
                current_user_id, is_admin, workspace_id=workspace_id
            )

    async def get_task(self, task_id: int, workspace_id: Optional[int] = None) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            task = await repo.get_task_with_relations(task_id, workspace_id=workspace_id)
            return task.to_dict() if task else None

    async def create_task(self, **kwargs) -> dict:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            return await repo.create_task(**kwargs)

    async def update_task(self, task_id: int, **kwargs) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            return await repo.update_task(task_id, **kwargs)

    async def delete_task(self, task_id: int) -> bool:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            return await repo.delete_by_id(task_id)

    async def reorder(self, task_id: int, new_status: str, new_position: int) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            return await repo.reorder(task_id, new_status, new_position)

    async def add_dependency(self, blocker_id: int, dependent_id: int) -> None:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            await repo.add_dependency(blocker_id, dependent_id)

    async def remove_dependency(self, blocker_id: int, dependent_id: int) -> bool:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            return await repo.remove_dependency(blocker_id, dependent_id)

    async def add_checklist_item(self, task_id: int, text: str, position: int = 0) -> dict:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            return await repo.add_checklist_item(task_id, text, position)

    async def toggle_checklist_item(self, item_id: int) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            return await repo.toggle_checklist_item(item_id)

    async def delete_checklist_item(self, item_id: int) -> bool:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            return await repo.delete_checklist_item(item_id)

    async def get_visible_tasks_for_project(
        self,
        project_id,
        current_user_id: int,
        is_admin: bool,
        workspace_id: Optional[int] = None,
    ) -> list:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            return await repo.get_visible_tasks_for_project(
                project_id, current_user_id, is_admin, workspace_id=workspace_id
            )

    async def find_by_github_issue(self, project_id: int, issue_number: int):
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            task = await repo.find_by_github_issue(project_id, issue_number)
            return task.to_dict() if task else None

    async def upsert_from_github(self, project_id: int, issue_number: int, **fields) -> dict:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            return await repo.upsert_from_github(project_id, issue_number, **fields)


async_kanban_manager = AsyncKanbanManager()


# ============== Kanban Project Manager ==============


class AsyncKanbanProjectManager:
    """Async kanban project manager."""

    async def get_all_projects(self, workspace_id: Optional[int] = None) -> list:
        async with AsyncSessionLocal() as session:
            repo = KanbanProjectRepository(session)
            return await repo.get_all_projects(workspace_id=workspace_id)

    async def get_project(
        self, project_id: int, workspace_id: Optional[int] = None
    ) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = KanbanProjectRepository(session)
            project = await repo.get_project_with_token(project_id, workspace_id=workspace_id)
            return project.to_dict() if project else None

    async def get_project_with_token(self, project_id: int):
        """Returns ORM object with raw token for sync operations."""
        async with AsyncSessionLocal() as session:
            repo = KanbanProjectRepository(session)
            project = await repo.get_project_with_token(project_id)
            if not project:
                return None
            # Return a plain dict with token included (for internal use only)
            d = project.to_dict()
            d["github_token"] = project.github_token
            d["webhook_secret"] = project.webhook_secret
            d["_label_mapping"] = project.get_label_mapping()
            d["_reverse_label_mapping"] = project.get_reverse_label_mapping()
            return d

    async def get_by_repo(self, owner: str, repo: str):
        """Find project by GitHub owner/repo. Returns dict with token."""
        async with AsyncSessionLocal() as session:
            repo_obj = KanbanProjectRepository(session)
            project = await repo_obj.get_by_repo(owner, repo)
            if not project:
                return None
            d = project.to_dict()
            d["github_token"] = project.github_token
            d["webhook_secret"] = project.webhook_secret
            d["_label_mapping"] = project.get_label_mapping()
            d["_reverse_label_mapping"] = project.get_reverse_label_mapping()
            return d

    async def create_project(self, **kwargs) -> dict:
        async with AsyncSessionLocal() as session:
            repo = KanbanProjectRepository(session)
            return await repo.create_project(**kwargs)

    async def update_project(self, project_id: int, **kwargs) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = KanbanProjectRepository(session)
            return await repo.update_project(project_id, **kwargs)

    async def delete_project(self, project_id: int) -> bool:
        async with AsyncSessionLocal() as session:
            repo = KanbanProjectRepository(session)
            return await repo.delete_by_id(project_id)

    async def update_last_synced(self, project_id: int) -> None:
        async with AsyncSessionLocal() as session:
            repo = KanbanProjectRepository(session)
            await repo.update_last_synced(project_id)


async_kanban_project_manager = AsyncKanbanProjectManager()


# ============== Role Manager ==============


class AsyncRoleManager:
    """Async role manager for RBAC."""

    async def get_by_name(self, name: str) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = RoleRepository(session)
            role = await repo.get_by_name(name)
            return role.to_dict() if role else None

    async def get_with_permissions(self, role_id: int) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = RoleRepository(session)
            role = await repo.get_with_permissions(role_id)
            return role.to_dict() if role else None

    async def get_all_with_permissions(self) -> List[dict]:
        async with AsyncSessionLocal() as session:
            repo = RoleRepository(session)
            roles = await repo.get_all_with_permissions()
            return [r.to_dict() for r in roles]

    async def create_role(
        self,
        name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        is_system: bool = False,
        permissions: Optional[Dict[str, str]] = None,
    ) -> dict:
        async with AsyncSessionLocal() as session:
            repo = RoleRepository(session)
            role = await repo.create_role(name, display_name, description, is_system, permissions)
            return role.to_dict()

    async def update_role(
        self,
        role_id: int,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        permissions: Optional[Dict[str, str]] = None,
    ) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = RoleRepository(session)
            role = await repo.update_role(role_id, display_name, description, permissions)
            return role.to_dict() if role else None

    async def delete_role(self, role_id: int) -> bool:
        async with AsyncSessionLocal() as session:
            repo = RoleRepository(session)
            return await repo.delete_role(role_id)

    async def count(self) -> int:
        async with AsyncSessionLocal() as session:
            repo = RoleRepository(session)
            return await repo.count()


async_role_manager = AsyncRoleManager()


# ============== Workspace Manager ==============


class AsyncWorkspaceManager:
    """Async manager for workspace operations."""

    async def get_member_role_name(self, user_id: int, workspace_id: int) -> Optional[str]:
        """Get role_name for (user_id, workspace_id) from workspace_members."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            return await repo.get_member_role_name(user_id, workspace_id)

    async def ensure_membership(self, workspace_id: int, user_id: int, role_name: str) -> None:
        """Insert or update workspace membership (idempotent)."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            await repo.ensure_membership(workspace_id, user_id, role_name)

    async def get_default_workspace(self) -> Optional[dict]:
        """Get workspace with id=1."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            return await repo.get_default_workspace()

    async def create_default(self, name: str = "Default", slug: str = "default") -> dict:
        """Create the default workspace."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            return await repo.create_default(name, slug)

    # ============== Members Management ==============

    async def get_workspace_info(self, workspace_id: int) -> Optional[dict]:
        """Get workspace by ID with member count."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            return await repo.get_workspace_info(workspace_id)

    async def list_members(self, workspace_id: int) -> List[dict]:
        """List all members of a workspace with user details."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            return await repo.list_members(workspace_id)

    async def update_member_role(
        self, workspace_id: int, user_id: int, role_name: str
    ) -> Optional[dict]:
        """Change a member's role."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            return await repo.update_member_role(workspace_id, user_id, role_name)

    async def remove_member(self, workspace_id: int, user_id: int) -> bool:
        """Remove a member from workspace."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            return await repo.remove_member(workspace_id, user_id)

    async def get_workspace_owner_id(self, workspace_id: int) -> Optional[int]:
        """Get the owner_id for a workspace."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            return await repo.get_workspace_owner_id(workspace_id)

    # ============== Invites ==============

    async def create_invite(
        self,
        workspace_id: int,
        role_name: str,
        created_by: int,
        email: Optional[str] = None,
        max_uses: Optional[int] = None,
        expires_hours: Optional[int] = None,
    ) -> dict:
        """Create an invite link."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            return await repo.create_invite(
                workspace_id, role_name, created_by, email, max_uses, expires_hours
            )

    async def list_invites(self, workspace_id: int) -> List[dict]:
        """List all invites for a workspace."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            return await repo.list_invites(workspace_id)

    async def delete_invite(self, workspace_id: int, invite_id: int) -> bool:
        """Delete an invite."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            return await repo.delete_invite(workspace_id, invite_id)

    async def get_invite_info(self, invite_code: str) -> Optional[dict]:
        """Get public invite info by code (workspace name, role, expiry)."""
        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            invite = await repo.get_invite_by_code(invite_code)
            if not invite or not invite.is_valid:
                return None
            ws = await repo.get_by_id(invite.workspace_id)
            return {
                "workspace_name": ws.name if ws else "Unknown",
                "role_name": invite.role_name,
                "expires_at": invite.expires_at.isoformat() if invite.expires_at else None,
            }

    async def accept_invite(
        self,
        invite_code: str,
        username: str,
        password: str,
        display_name: Optional[str] = None,
    ) -> Optional[dict]:
        """Accept an invite: create user + membership. Returns user dict or None."""
        from db.models import User, WorkspaceMember
        from utils.password import hash_password

        async with AsyncSessionLocal() as session:
            repo = WorkspaceRepository(session)
            invite = await repo.get_invite_by_code(invite_code)
            if not invite or not invite.is_valid:
                return None
            # Create user
            pw_hash, salt = hash_password(password)
            user = User(
                username=username,
                password_hash=pw_hash,
                salt=salt,
                role="user",
                display_name=display_name or username,
                is_active=True,
            )
            session.add(user)
            await session.flush()  # get user.id
            # Create membership
            session.add(
                WorkspaceMember(
                    workspace_id=invite.workspace_id,
                    user_id=user.id,
                    role_name=invite.role_name,
                )
            )
            # Record usage
            invite.used_count += 1
            invite.used_at = datetime.utcnow()
            invite.used_by = user.id
            await session.commit()
            await session.refresh(user)
            return {
                "user": user.to_dict(),
                "workspace_id": invite.workspace_id,
                "role_name": invite.role_name,
            }


async_workspace_manager = AsyncWorkspaceManager()


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
