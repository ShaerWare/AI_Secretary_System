"""
Widget instance repository for managing website widget instances.
"""

import logging
import re
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import WidgetInstance
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


# Default widget configuration
DEFAULT_WIDGET_CONFIG = {
    "title": "AI Ассистент",
    "greeting": "Здравствуйте! Чем могу помочь?",
    "placeholder": "Введите сообщение...",
    "primary_color": "#6366f1",
    "position": "right",
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


class WidgetInstanceRepository(BaseRepository[WidgetInstance]):
    """Repository for website widget instances."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, WidgetInstance)

    def _generate_id(self, name: str) -> str:
        """Generate unique ID from name."""
        return slugify(name) or f"widget-{int(datetime.utcnow().timestamp())}"

    async def get_by_name(self, name: str) -> Optional[WidgetInstance]:
        """Get widget instance by name."""
        result = await self.session.execute(
            select(WidgetInstance).where(WidgetInstance.name == name)
        )
        return result.scalar_one_or_none()

    async def list_instances(self, enabled_only: bool = False) -> List[dict]:
        """List all widget instances."""
        query = select(WidgetInstance).order_by(WidgetInstance.updated.desc())
        if enabled_only:
            query = query.where(WidgetInstance.enabled == True)

        result = await self.session.execute(query)
        instances = result.scalars().all()
        return [i.to_dict() for i in instances]

    async def get_instance(self, instance_id: str) -> Optional[dict]:
        """Get widget instance by ID."""
        instance = await self.session.get(WidgetInstance, instance_id)
        return instance.to_dict() if instance else None

    async def create_instance(self, name: str, description: str = None, **kwargs) -> dict:
        """Create new widget instance."""
        instance_id = kwargs.pop("id", None) or self._generate_id(name)

        # Check if ID exists
        existing = await self.session.get(WidgetInstance, instance_id)
        if existing:
            # Append timestamp to make unique
            instance_id = f"{instance_id}-{int(datetime.utcnow().timestamp())}"

        instance = WidgetInstance(
            id=instance_id,
            name=name,
            description=description,
            enabled=kwargs.get("enabled", True),
            # Appearance
            title=kwargs.get("title", DEFAULT_WIDGET_CONFIG["title"]),
            greeting=kwargs.get("greeting", DEFAULT_WIDGET_CONFIG["greeting"]),
            placeholder=kwargs.get("placeholder", DEFAULT_WIDGET_CONFIG["placeholder"]),
            primary_color=kwargs.get("primary_color", DEFAULT_WIDGET_CONFIG["primary_color"]),
            position=kwargs.get("position", DEFAULT_WIDGET_CONFIG["position"]),
            # Access
            tunnel_url=kwargs.get("tunnel_url", ""),
            # AI
            llm_backend=kwargs.get("llm_backend", DEFAULT_WIDGET_CONFIG["llm_backend"]),
            llm_persona=kwargs.get("llm_persona", DEFAULT_WIDGET_CONFIG["llm_persona"]),
            system_prompt=kwargs.get("system_prompt"),
            # TTS
            tts_engine=kwargs.get("tts_engine", DEFAULT_WIDGET_CONFIG["tts_engine"]),
            tts_voice=kwargs.get("tts_voice", DEFAULT_WIDGET_CONFIG["tts_voice"]),
            tts_preset=kwargs.get("tts_preset"),
            # Timestamps
            created=datetime.utcnow(),
            updated=datetime.utcnow(),
        )

        # Set JSON fields
        if "allowed_domains" in kwargs:
            instance.set_allowed_domains(kwargs["allowed_domains"])
        if "llm_params" in kwargs:
            instance.set_llm_params(kwargs["llm_params"])

        self.session.add(instance)
        await self.session.commit()
        await self.session.refresh(instance)

        logger.info(f"Created widget instance: {instance_id}")
        return instance.to_dict()

    async def update_instance(self, instance_id: str, **kwargs) -> Optional[dict]:
        """Update widget instance."""
        instance = await self.session.get(WidgetInstance, instance_id)
        if not instance:
            return None

        # Update simple fields
        simple_fields = [
            "name",
            "description",
            "enabled",
            "title",
            "greeting",
            "placeholder",
            "primary_color",
            "position",
            "tunnel_url",
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
        if "allowed_domains" in kwargs:
            instance.set_allowed_domains(kwargs["allowed_domains"])
        if "llm_params" in kwargs:
            instance.set_llm_params(kwargs["llm_params"])

        instance.updated = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(instance)

        logger.info(f"Updated widget instance: {instance_id}")
        return instance.to_dict()

    async def delete_instance(self, instance_id: str) -> bool:
        """Delete widget instance."""
        instance = await self.session.get(WidgetInstance, instance_id)
        if not instance:
            return False

        await self.session.delete(instance)
        await self.session.commit()

        logger.info(f"Deleted widget instance: {instance_id}")
        return True

    async def set_enabled(self, instance_id: str, enabled: bool) -> bool:
        """Enable or disable widget instance."""
        result = await self.session.execute(
            update(WidgetInstance)
            .where(WidgetInstance.id == instance_id)
            .values(enabled=enabled, updated=datetime.utcnow())
        )
        await self.session.commit()
        return result.rowcount > 0

    async def get_enabled_instances(self) -> List[dict]:
        """Get all enabled widget instances."""
        return await self.list_instances(enabled_only=True)

    async def instance_exists(self, instance_id: str) -> bool:
        """Check if instance exists."""
        instance = await self.session.get(WidgetInstance, instance_id)
        return instance is not None

    async def get_instance_count(self) -> int:
        """Get total number of widget instances."""
        return await self.count()

    async def import_from_legacy_config(self, config: dict, instance_id: str = "default") -> dict:
        """
        Import from legacy widget_config format.
        Creates a new instance or updates existing "default" instance.
        """
        existing = await self.session.get(WidgetInstance, instance_id)

        if existing:
            # Update existing
            return await self.update_instance(
                instance_id,
                name=config.get("name", "Default Widget"),
                enabled=config.get("enabled", False),
                title=config.get("title", DEFAULT_WIDGET_CONFIG["title"]),
                greeting=config.get("greeting", DEFAULT_WIDGET_CONFIG["greeting"]),
                placeholder=config.get("placeholder", DEFAULT_WIDGET_CONFIG["placeholder"]),
                primary_color=config.get("primary_color", DEFAULT_WIDGET_CONFIG["primary_color"]),
                position=config.get("position", DEFAULT_WIDGET_CONFIG["position"]),
                allowed_domains=config.get("allowed_domains", []),
                tunnel_url=config.get("tunnel_url", ""),
            )
        else:
            # Create new
            return await self.create_instance(
                id=instance_id,
                name=config.get("name", "Default Widget"),
                description="Default website widget (migrated from legacy config)",
                enabled=config.get("enabled", False),
                title=config.get("title", DEFAULT_WIDGET_CONFIG["title"]),
                greeting=config.get("greeting", DEFAULT_WIDGET_CONFIG["greeting"]),
                placeholder=config.get("placeholder", DEFAULT_WIDGET_CONFIG["placeholder"]),
                primary_color=config.get("primary_color", DEFAULT_WIDGET_CONFIG["primary_color"]),
                position=config.get("position", DEFAULT_WIDGET_CONFIG["position"]),
                allowed_domains=config.get("allowed_domains", []),
                tunnel_url=config.get("tunnel_url", ""),
            )
