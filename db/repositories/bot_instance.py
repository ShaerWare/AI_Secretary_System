"""
Bot instance repository for managing Telegram bot instances.
"""

import logging
import re
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BotInstance
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


# Default bot configuration
DEFAULT_BOT_CONFIG = {
    "welcome_message": "Здравствуйте! Я AI-ассистент. Чем могу помочь?",
    "unauthorized_message": "Извините, у вас нет доступа к этому боту.",
    "error_message": "Произошла ошибка. Попробуйте позже.",
    "typing_enabled": True,
    "llm_backend": "vllm",
    "llm_persona": "gulya",
    "tts_engine": "xtts",
    "tts_voice": "gulya",
}


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:50]


class BotInstanceRepository(BaseRepository[BotInstance]):
    """Repository for Telegram bot instances."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, BotInstance)

    def _generate_id(self, name: str) -> str:
        """Generate unique ID from name."""
        return slugify(name) or f"bot-{int(datetime.utcnow().timestamp())}"

    async def get_by_name(self, name: str) -> Optional[BotInstance]:
        """Get bot instance by name."""
        result = await self.session.execute(select(BotInstance).where(BotInstance.name == name))
        return result.scalar_one_or_none()

    async def list_instances(self, enabled_only: bool = False) -> List[dict]:
        """List all bot instances."""
        query = select(BotInstance).order_by(BotInstance.updated.desc())
        if enabled_only:
            query = query.where(BotInstance.enabled == True)

        result = await self.session.execute(query)
        instances = result.scalars().all()
        return [i.to_dict() for i in instances]

    async def get_instance(self, instance_id: str) -> Optional[dict]:
        """Get bot instance by ID."""
        instance = await self.session.get(BotInstance, instance_id)
        return instance.to_dict() if instance else None

    async def get_instance_with_token(self, instance_id: str) -> Optional[dict]:
        """Get bot instance with token (for internal use)."""
        instance = await self.session.get(BotInstance, instance_id)
        return instance.to_dict(include_token=True) if instance else None

    async def create_instance(
        self, name: str, description: str = None, bot_token: str = None, **kwargs
    ) -> dict:
        """Create new bot instance."""
        instance_id = kwargs.pop("id", None) or self._generate_id(name)

        # Check if ID exists
        existing = await self.session.get(BotInstance, instance_id)
        if existing:
            # Append timestamp to make unique
            instance_id = f"{instance_id}-{int(datetime.utcnow().timestamp())}"

        instance = BotInstance(
            id=instance_id,
            name=name,
            description=description,
            enabled=kwargs.get("enabled", True),
            # Telegram
            bot_token=bot_token,
            welcome_message=kwargs.get("welcome_message", DEFAULT_BOT_CONFIG["welcome_message"]),
            unauthorized_message=kwargs.get(
                "unauthorized_message", DEFAULT_BOT_CONFIG["unauthorized_message"]
            ),
            error_message=kwargs.get("error_message", DEFAULT_BOT_CONFIG["error_message"]),
            typing_enabled=kwargs.get("typing_enabled", DEFAULT_BOT_CONFIG["typing_enabled"]),
            # AI
            llm_backend=kwargs.get("llm_backend", DEFAULT_BOT_CONFIG["llm_backend"]),
            llm_persona=kwargs.get("llm_persona", DEFAULT_BOT_CONFIG["llm_persona"]),
            system_prompt=kwargs.get("system_prompt"),
            # TTS
            tts_engine=kwargs.get("tts_engine", DEFAULT_BOT_CONFIG["tts_engine"]),
            tts_voice=kwargs.get("tts_voice", DEFAULT_BOT_CONFIG["tts_voice"]),
            tts_preset=kwargs.get("tts_preset"),
            # Timestamps
            created=datetime.utcnow(),
            updated=datetime.utcnow(),
        )

        # Set JSON fields
        if "allowed_users" in kwargs:
            instance.set_allowed_users(kwargs["allowed_users"])
        if "admin_users" in kwargs:
            instance.set_admin_users(kwargs["admin_users"])
        if "llm_params" in kwargs:
            instance.set_llm_params(kwargs["llm_params"])

        self.session.add(instance)
        await self.session.commit()
        await self.session.refresh(instance)

        logger.info(f"Created bot instance: {instance_id}")
        return instance.to_dict()

    async def update_instance(self, instance_id: str, **kwargs) -> Optional[dict]:
        """Update bot instance."""
        instance = await self.session.get(BotInstance, instance_id)
        if not instance:
            return None

        # Update simple fields
        simple_fields = [
            "name",
            "description",
            "enabled",
            "bot_token",
            "api_url",
            "welcome_message",
            "unauthorized_message",
            "error_message",
            "typing_enabled",
            "llm_backend",
            "llm_persona",
            "system_prompt",
            "tts_engine",
            "tts_voice",
            "tts_preset",
        ]
        for field in simple_fields:
            if field in kwargs:
                setattr(instance, field, kwargs[field])

        # Update JSON fields
        if "allowed_users" in kwargs:
            instance.set_allowed_users(kwargs["allowed_users"])
        if "admin_users" in kwargs:
            instance.set_admin_users(kwargs["admin_users"])
        if "llm_params" in kwargs:
            instance.set_llm_params(kwargs["llm_params"])

        instance.updated = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(instance)

        logger.info(f"Updated bot instance: {instance_id}")
        return instance.to_dict()

    async def delete_instance(self, instance_id: str) -> bool:
        """Delete bot instance."""
        instance = await self.session.get(BotInstance, instance_id)
        if not instance:
            return False

        await self.session.delete(instance)
        await self.session.commit()

        logger.info(f"Deleted bot instance: {instance_id}")
        return True

    async def set_enabled(self, instance_id: str, enabled: bool) -> bool:
        """Enable or disable bot instance."""
        result = await self.session.execute(
            update(BotInstance)
            .where(BotInstance.id == instance_id)
            .values(enabled=enabled, updated=datetime.utcnow())
        )
        await self.session.commit()
        return result.rowcount > 0

    async def get_enabled_instances(self) -> List[dict]:
        """Get all enabled bot instances."""
        return await self.list_instances(enabled_only=True)

    async def instance_exists(self, instance_id: str) -> bool:
        """Check if instance exists."""
        instance = await self.session.get(BotInstance, instance_id)
        return instance is not None

    async def get_instance_count(self) -> int:
        """Get total number of bot instances."""
        return await self.count()

    async def import_from_legacy_config(self, config: dict, instance_id: str = "default") -> dict:
        """
        Import from legacy telegram_config format.
        Creates a new instance or updates existing "default" instance.
        """
        existing = await self.session.get(BotInstance, instance_id)

        if existing:
            # Update existing
            return await self.update_instance(
                instance_id,
                name=config.get("name", "Default Bot"),
                enabled=config.get("enabled", False),
                bot_token=config.get("bot_token", ""),
                allowed_users=config.get("allowed_users", []),
                admin_users=config.get("admin_users", []),
                welcome_message=config.get(
                    "welcome_message", DEFAULT_BOT_CONFIG["welcome_message"]
                ),
                unauthorized_message=config.get(
                    "unauthorized_message", DEFAULT_BOT_CONFIG["unauthorized_message"]
                ),
                error_message=config.get("error_message", DEFAULT_BOT_CONFIG["error_message"]),
                typing_enabled=config.get("typing_enabled", True),
            )
        else:
            # Create new
            return await self.create_instance(
                id=instance_id,
                name=config.get("name", "Default Bot"),
                description="Default Telegram bot (migrated from legacy config)",
                enabled=config.get("enabled", False),
                bot_token=config.get("bot_token", ""),
                allowed_users=config.get("allowed_users", []),
                admin_users=config.get("admin_users", []),
                welcome_message=config.get(
                    "welcome_message", DEFAULT_BOT_CONFIG["welcome_message"]
                ),
                unauthorized_message=config.get(
                    "unauthorized_message", DEFAULT_BOT_CONFIG["unauthorized_message"]
                ),
                error_message=config.get("error_message", DEFAULT_BOT_CONFIG["error_message"]),
                typing_enabled=config.get("typing_enabled", True),
            )
