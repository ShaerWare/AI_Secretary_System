"""
WhatsApp instance repository for managing WhatsApp bot instances.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ResourceShare, WhatsAppInstance
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


# Default WhatsApp bot configuration
DEFAULT_WA_CONFIG = {
    "llm_backend": "vllm",
    "tts_engine": "xtts",
    "tts_voice": "anna",
    "webhook_port": 8003,
}


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:50]


class WhatsAppInstanceRepository(BaseRepository[WhatsAppInstance]):
    """Repository for WhatsApp bot instances."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, WhatsAppInstance)

    def _generate_id(self, name: str) -> str:
        """Generate unique ID from name."""
        return slugify(name) or f"wa-{int(datetime.utcnow().timestamp())}"

    async def get_by_name(self, name: str) -> Optional[WhatsAppInstance]:
        """Get WhatsApp instance by name."""
        result = await self.session.execute(
            select(WhatsAppInstance).where(WhatsAppInstance.name == name)
        )
        instance: Optional[WhatsAppInstance] = result.scalar_one_or_none()
        return instance

    async def list_instances(
        self,
        enabled_only: bool = False,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> List[dict]:
        """List WhatsApp instances, filtered by owner and workspace."""
        query = select(WhatsAppInstance).order_by(WhatsAppInstance.updated.desc())
        if enabled_only:
            query = query.where(WhatsAppInstance.enabled == True)
        if owner_id is not None:
            shared_subq = (
                select(ResourceShare.resource_id)
                .where(
                    ResourceShare.resource_type == "whatsapp_instance",
                    ResourceShare.user_id == owner_id,
                )
                .scalar_subquery()
            )
            query = query.where(
                (WhatsAppInstance.owner_id == owner_id)
                | (WhatsAppInstance.owner_id.is_(None))
                | (WhatsAppInstance.id.in_(shared_subq))
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
        """Get WhatsApp instance by ID, with optional owner/workspace check."""
        query = select(WhatsAppInstance).where(WhatsAppInstance.id == instance_id)
        if owner_id is not None:
            shared_subq = (
                select(ResourceShare.resource_id)
                .where(
                    ResourceShare.resource_type == "whatsapp_instance",
                    ResourceShare.user_id == owner_id,
                )
                .scalar_subquery()
            )
            query = query.where(
                (WhatsAppInstance.owner_id == owner_id)
                | (WhatsAppInstance.owner_id.is_(None))
                | (WhatsAppInstance.id.in_(shared_subq))
            )
        query = self._apply_workspace_filter(query, workspace_id)
        result = await self.session.execute(query)
        instance = result.scalar_one_or_none()
        if not instance:
            return None
        return instance.to_dict()

    async def get_instance_with_token(self, instance_id: str) -> Optional[dict]:
        """Get WhatsApp instance with token (for internal use)."""
        instance = await self.session.get(WhatsAppInstance, instance_id)
        return instance.to_dict(include_token=True) if instance else None

    async def create_instance(
        self,
        name: str,
        description: Optional[str] = None,
        phone_number_id: str = "",
        **kwargs: Any,
    ) -> dict:
        """Create new WhatsApp instance."""
        instance_id = kwargs.pop("id", None) or self._generate_id(name)

        # Check if ID exists
        existing = await self.session.get(WhatsAppInstance, instance_id)
        if existing:
            instance_id = f"{instance_id}-{int(datetime.utcnow().timestamp())}"

        # Build creation kwargs
        create_kwargs: dict[str, Any] = {}
        if kwargs.get("workspace_id") is not None:
            create_kwargs["workspace_id"] = kwargs["workspace_id"]

        instance = WhatsAppInstance(
            id=instance_id,
            name=name,
            description=description,
            enabled=kwargs.get("enabled", True),
            auto_start=kwargs.get("auto_start", False),
            owner_id=kwargs.get("owner_id"),
            **create_kwargs,
            # WhatsApp API
            phone_number_id=phone_number_id,
            waba_id=kwargs.get("waba_id"),
            access_token=kwargs.get("access_token"),
            verify_token=kwargs.get("verify_token"),
            app_secret=kwargs.get("app_secret"),
            # Webhook
            webhook_port=kwargs.get("webhook_port", DEFAULT_WA_CONFIG["webhook_port"]),
            # AI
            llm_backend=kwargs.get("llm_backend", DEFAULT_WA_CONFIG["llm_backend"]),
            system_prompt=kwargs.get("system_prompt"),
            # TTS
            tts_enabled=kwargs.get("tts_enabled", False),
            tts_engine=kwargs.get("tts_engine", DEFAULT_WA_CONFIG["tts_engine"]),
            tts_voice=kwargs.get("tts_voice", DEFAULT_WA_CONFIG["tts_voice"]),
            tts_preset=kwargs.get("tts_preset"),
            # Rate limiting
            rate_limit_count=kwargs.get("rate_limit_count"),
            rate_limit_hours=kwargs.get("rate_limit_hours"),
            # Timestamps
            created=datetime.utcnow(),
            updated=datetime.utcnow(),
        )

        # Set JSON fields
        if "allowed_phones" in kwargs:
            instance.set_allowed_phones(kwargs["allowed_phones"])
        if "blocked_phones" in kwargs:
            instance.set_blocked_phones(kwargs["blocked_phones"])
        if "llm_params" in kwargs:
            instance.set_llm_params(kwargs["llm_params"])

        self.session.add(instance)
        await self.session.flush()

        logger.info(f"Created WhatsApp instance: {instance_id}")
        return instance.to_dict()

    async def update_instance(self, instance_id: str, **kwargs: Any) -> Optional[dict]:
        """Update WhatsApp instance."""
        instance = await self.session.get(WhatsAppInstance, instance_id)
        if not instance:
            return None

        simple_fields = [
            "name",
            "description",
            "enabled",
            "auto_start",
            "phone_number_id",
            "waba_id",
            "access_token",
            "verify_token",
            "app_secret",
            "webhook_port",
            "llm_backend",
            "system_prompt",
            "tts_enabled",
            "tts_engine",
            "tts_voice",
            "tts_preset",
            "rate_limit_count",
            "rate_limit_hours",
            "rag_mode",
        ]
        for field in simple_fields:
            if field in kwargs:
                setattr(instance, field, kwargs[field])

        # Update JSON fields
        if "allowed_phones" in kwargs:
            instance.set_allowed_phones(kwargs["allowed_phones"])
        if "blocked_phones" in kwargs:
            instance.set_blocked_phones(kwargs["blocked_phones"])
        if "llm_params" in kwargs:
            instance.set_llm_params(kwargs["llm_params"])
        if "knowledge_collection_ids" in kwargs:
            ids = kwargs["knowledge_collection_ids"]
            instance.knowledge_collection_ids = json.dumps(ids) if ids else None

        instance.updated = datetime.utcnow()
        await self.session.flush()

        logger.info(f"Updated WhatsApp instance: {instance_id}")
        data: dict[str, Any] = instance.to_dict()
        return data

    async def delete_instance(
        self,
        instance_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> bool:
        """Delete WhatsApp instance, with optional owner/workspace check."""
        query = select(WhatsAppInstance).where(WhatsAppInstance.id == instance_id)
        if owner_id is not None:
            query = query.where(
                (WhatsAppInstance.owner_id == owner_id) | (WhatsAppInstance.owner_id.is_(None))
            )
        if workspace_id is not None and hasattr(WhatsAppInstance, "workspace_id"):
            query = query.where(WhatsAppInstance.workspace_id == workspace_id)
        result = await self.session.execute(query)
        instance = result.scalar_one_or_none()
        if not instance:
            return False

        await self.session.delete(instance)
        await self.session.flush()

        logger.info(f"Deleted WhatsApp instance: {instance_id}")
        return True

    async def set_enabled(self, instance_id: str, enabled: bool) -> bool:
        """Enable or disable WhatsApp instance."""
        result = await self.session.execute(
            update(WhatsAppInstance)
            .where(WhatsAppInstance.id == instance_id)
            .values(enabled=enabled, updated=datetime.utcnow())
        )
        await self.session.flush()
        return bool(result.rowcount > 0)  # type: ignore[attr-defined]

    async def set_auto_start(self, instance_id: str, auto_start: bool) -> bool:
        """Set auto-start flag for WhatsApp instance."""
        result = await self.session.execute(
            update(WhatsAppInstance)
            .where(WhatsAppInstance.id == instance_id)
            .values(auto_start=auto_start, updated=datetime.utcnow())
        )
        await self.session.flush()
        return bool(result.rowcount > 0)  # type: ignore[attr-defined]

    async def get_auto_start_instances(self) -> List[dict]:
        """Get all WhatsApp instances that should auto-start."""
        query = (
            select(WhatsAppInstance)
            .where(WhatsAppInstance.enabled == True)
            .where(WhatsAppInstance.auto_start == True)
            .order_by(WhatsAppInstance.name)
        )
        result = await self.session.execute(query)
        instances = result.scalars().all()
        return [i.to_dict() for i in instances]

    async def get_enabled_instances(self) -> List[dict]:
        """Get all enabled WhatsApp instances."""
        return await self.list_instances(enabled_only=True)

    async def instance_exists(self, instance_id: str) -> bool:
        """Check if instance exists."""
        instance = await self.session.get(WhatsAppInstance, instance_id)
        return instance is not None

    async def get_instance_count(self) -> int:
        """Get total number of WhatsApp instances."""
        return await self.count()
