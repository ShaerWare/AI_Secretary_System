"""
Bot instance repository for managing Telegram bot instances.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import DEFAULT_ACTION_BUTTONS, BotInstance
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


# Default bot configuration
DEFAULT_BOT_CONFIG = {
    "welcome_message": "Здравствуйте! Я AI-ассистент. Чем могу помочь?",
    "unauthorized_message": "Извините, у вас нет доступа к этому боту.",
    "error_message": "Произошла ошибка. Попробуйте позже.",
    "typing_enabled": True,
    "llm_backend": "vllm",
    "llm_persona": "anna",
    "tts_engine": "xtts",
    "tts_voice": "anna",
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
        instance: Optional[BotInstance] = result.scalar_one_or_none()
        return instance

    async def list_instances(
        self,
        enabled_only: bool = False,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> List[dict]:
        """List bot instances, filtered by owner and workspace."""
        query = select(BotInstance).order_by(BotInstance.updated.desc())
        if enabled_only:
            query = query.where(BotInstance.enabled == True)
        if owner_id is not None:
            query = query.where(
                (BotInstance.owner_id == owner_id) | (BotInstance.owner_id.is_(None))
            )
        query = self._apply_workspace_filter(query, workspace_id)

        result = await self.session.execute(query)
        instances = result.scalars().all()
        return [i.to_dict() for i in instances]

    async def get_instance(
        self,
        instance_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> Optional[dict]:
        """Get bot instance by ID, with optional owner/workspace check."""
        query = select(BotInstance).where(BotInstance.id == instance_id)
        if owner_id is not None:
            query = query.where(
                (BotInstance.owner_id == owner_id) | (BotInstance.owner_id.is_(None))
            )
        query = self._apply_workspace_filter(query, workspace_id)
        result = await self.session.execute(query)
        instance = result.scalar_one_or_none()
        if not instance:
            return None
        return instance.to_dict()

    async def get_instance_with_token(self, instance_id: str) -> Optional[dict]:
        """Get bot instance with token (for internal use)."""
        instance = await self.session.get(BotInstance, instance_id)
        return instance.to_dict(include_token=True) if instance else None

    async def create_instance(
        self,
        name: str,
        description: Optional[str] = None,
        bot_token: Optional[str] = None,
        **kwargs: Any,
    ) -> dict:
        """Create new bot instance."""
        instance_id = kwargs.pop("id", None) or self._generate_id(name)

        # Check if ID exists
        existing = await self.session.get(BotInstance, instance_id)
        if existing:
            # Append timestamp to make unique
            instance_id = f"{instance_id}-{int(datetime.utcnow().timestamp())}"

        # Build creation kwargs
        create_kwargs: dict[str, Any] = {}
        if kwargs.get("workspace_id") is not None:
            create_kwargs["workspace_id"] = kwargs["workspace_id"]

        instance = BotInstance(
            id=instance_id,
            name=name,
            description=description,
            enabled=kwargs.get("enabled", True),
            owner_id=kwargs.get("owner_id"),
            **create_kwargs,
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
            # Payment
            payment_enabled=kwargs.get("payment_enabled", False),
            yookassa_provider_token=kwargs.get("yookassa_provider_token"),
            stars_enabled=kwargs.get("stars_enabled", False),
            payment_success_message=kwargs.get("payment_success_message"),
            # Sales funnel
            sales_funnel_enabled=kwargs.get("sales_funnel_enabled", True),
            # RAG
            rag_mode=kwargs.get("rag_mode", "all"),
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
        if "action_buttons" in kwargs:
            instance.set_action_buttons(kwargs["action_buttons"])
        else:
            # Set default action buttons for new instances
            instance.set_action_buttons(DEFAULT_ACTION_BUTTONS)
        if "payment_products" in kwargs:
            instance.set_payment_products(kwargs["payment_products"])
        if "knowledge_collection_ids" in kwargs:
            ids = kwargs["knowledge_collection_ids"]
            instance.knowledge_collection_ids = json.dumps(ids) if ids else None

        self.session.add(instance)
        await self.session.commit()
        await self.session.refresh(instance)

        logger.info(f"Created bot instance: {instance_id}")
        return instance.to_dict()

    async def update_instance(self, instance_id: str, **kwargs: Any) -> Optional[dict]:
        """Update bot instance."""
        instance = await self.session.get(BotInstance, instance_id)
        if not instance:
            return None

        # Update simple fields
        simple_fields = [
            "name",
            "description",
            "enabled",
            "auto_start",
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
            "payment_enabled",
            "yookassa_provider_token",
            "stars_enabled",
            "payment_success_message",
            # Sales funnel
            "sales_funnel_enabled",
            # RAG
            "rag_mode",
            # YooMoney
            "yoomoney_client_id",
            "yoomoney_client_secret",
            "yoomoney_access_token",
            "yoomoney_wallet_id",
            "yoomoney_redirect_uri",
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
        if "action_buttons" in kwargs:
            instance.set_action_buttons(kwargs["action_buttons"])
        if "payment_products" in kwargs:
            instance.set_payment_products(kwargs["payment_products"])
        if "knowledge_collection_ids" in kwargs:
            ids = kwargs["knowledge_collection_ids"]
            instance.knowledge_collection_ids = json.dumps(ids) if ids else None

        instance.updated = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(instance)

        logger.info(f"Updated bot instance: {instance_id}")
        data: dict[str, Any] = instance.to_dict()
        return data

    async def delete_instance(
        self,
        instance_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> bool:
        """Delete bot instance, with optional owner/workspace check."""
        query = select(BotInstance).where(BotInstance.id == instance_id)
        if owner_id is not None:
            query = query.where(
                (BotInstance.owner_id == owner_id) | (BotInstance.owner_id.is_(None))
            )
        if workspace_id is not None and hasattr(BotInstance, "workspace_id"):
            query = query.where(BotInstance.workspace_id == workspace_id)
        result = await self.session.execute(query)
        instance = result.scalar_one_or_none()
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
        return bool(result.rowcount > 0)  # type: ignore[attr-defined]

    async def set_auto_start(self, instance_id: str, auto_start: bool) -> bool:
        """Set auto-start flag for bot instance."""
        result = await self.session.execute(
            update(BotInstance)
            .where(BotInstance.id == instance_id)
            .values(auto_start=auto_start, updated=datetime.utcnow())
        )
        await self.session.commit()
        return bool(result.rowcount > 0)  # type: ignore[attr-defined]

    async def get_auto_start_instances(self) -> List[dict]:
        """Get all bot instances that should auto-start."""
        query = (
            select(BotInstance)
            .where(BotInstance.enabled == True)
            .where(BotInstance.auto_start == True)
            .order_by(BotInstance.name)
        )
        result = await self.session.execute(query)
        instances = result.scalars().all()
        return [i.to_dict() for i in instances]

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

    async def import_from_legacy_config(
        self, config: dict[str, Any], instance_id: str = "default"
    ) -> dict[str, Any]:
        """
        Import from legacy telegram_config format.
        Creates a new instance or updates existing "default" instance.
        """
        existing = await self.session.get(BotInstance, instance_id)

        if existing:
            # Update existing
            update_result = await self.update_instance(
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
            return update_result or {}
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
