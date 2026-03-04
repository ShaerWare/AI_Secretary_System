"""Telegram channel services."""

import logging
from typing import Any, Dict, List, Optional

from db.database import AsyncSessionLocal
from db.repositories import BotInstanceRepository, TelegramRepository, UserIdentityRepository
from db.retry import retry_on_busy


logger = logging.getLogger(__name__)


class BotInstanceService:
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
            result = await repo.create_instance(name, **kwargs)
            await session.commit()
            return result

    async def update_instance(self, instance_id: str, **kwargs: Any) -> Optional[dict]:
        """Update bot instance."""
        async with AsyncSessionLocal() as session:
            repo = BotInstanceRepository(session)
            result = await repo.update_instance(instance_id, **kwargs)
            await session.commit()
            return result

    async def delete_instance(
        self,
        instance_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> bool:
        """Delete bot instance."""
        async with AsyncSessionLocal() as session:
            repo = BotInstanceRepository(session)
            result = await repo.delete_instance(
                instance_id, owner_id=owner_id, workspace_id=workspace_id
            )
            await session.commit()
            return result

    async def set_enabled(self, instance_id: str, enabled: bool) -> bool:
        """Enable or disable bot instance."""
        async with AsyncSessionLocal() as session:
            repo = BotInstanceRepository(session)
            result = await repo.set_enabled(instance_id, enabled)
            await session.commit()
            return result

    async def set_auto_start(self, instance_id: str, auto_start: bool) -> bool:
        """Set auto-start flag for bot instance."""
        async with AsyncSessionLocal() as session:
            repo = BotInstanceRepository(session)
            result = await repo.set_auto_start(instance_id, auto_start)
            await session.commit()
            return result

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
            result = await repo.import_from_legacy_config(config, instance_id)
            await session.commit()
            return result


class TelegramSessionService:
    """Async Telegram session manager using database (supports multi-bot)."""

    async def get_session(self, user_id: int, bot_id: str = "default") -> Optional[str]:
        """Get chat session ID for user in specific bot."""
        async with AsyncSessionLocal() as session:
            repo = TelegramRepository(session, bot_id=bot_id)
            return await repo.get_session(user_id, bot_id=bot_id)

    @retry_on_busy()
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

            await session.commit()

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
            result = await repo.clear_all_sessions(bot_id=bot_id)
            await session.commit()
            return result

    async def clear_sessions_for_bot(self, bot_id: str) -> int:
        """Clear sessions for specific bot instance."""
        async with AsyncSessionLocal() as session:
            repo = TelegramRepository(session)
            result = await repo.clear_sessions_for_bot(bot_id)
            await session.commit()
            return result

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


# Singletons
bot_instance_service = BotInstanceService()
telegram_session_service = TelegramSessionService()
