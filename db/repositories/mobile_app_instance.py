"""
Mobile app instance repository.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import MobileAppInstance, ResourceShare
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


DEFAULT_MOBILE_CONFIG = {
    "llm_backend": "vllm",
    "llm_persona": "",
    "tts_engine": "xtts",
    "tts_voice": "anna",
}


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:50]


class MobileAppInstanceRepository(BaseRepository[MobileAppInstance]):
    """Repository for mobile app instances."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, MobileAppInstance)

    def _generate_id(self, name: str) -> str:
        return slugify(name) or f"mobile-{int(datetime.utcnow().timestamp())}"

    async def list_instances(
        self,
        enabled_only: bool = False,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> List[dict]:
        query = select(MobileAppInstance).order_by(MobileAppInstance.updated.desc())
        if enabled_only:
            query = query.where(MobileAppInstance.enabled == True)
        if owner_id is not None:
            shared_subq = (
                select(ResourceShare.resource_id)
                .where(
                    ResourceShare.resource_type == "mobile_app_instance",
                    ResourceShare.user_id == owner_id,
                )
                .scalar_subquery()
            )
            query = query.where(
                (MobileAppInstance.owner_id == owner_id)
                | (MobileAppInstance.owner_id.is_(None))
                | (MobileAppInstance.id.in_(shared_subq))
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
        query = select(MobileAppInstance).where(MobileAppInstance.id == instance_id)
        if owner_id is not None:
            shared_subq = (
                select(ResourceShare.resource_id)
                .where(
                    ResourceShare.resource_type == "mobile_app_instance",
                    ResourceShare.user_id == owner_id,
                )
                .scalar_subquery()
            )
            query = query.where(
                (MobileAppInstance.owner_id == owner_id)
                | (MobileAppInstance.owner_id.is_(None))
                | (MobileAppInstance.id.in_(shared_subq))
            )
        query = self._apply_workspace_filter(query, workspace_id)
        result = await self.session.execute(query)
        instance = result.scalar_one_or_none()
        if not instance:
            return None
        return instance.to_dict()

    async def create_instance(
        self, name: str, description: Optional[str] = None, **kwargs: Any
    ) -> dict:
        instance_id = kwargs.pop("id", None) or self._generate_id(name)

        existing = await self.session.get(MobileAppInstance, instance_id)
        if existing:
            instance_id = f"{instance_id}-{int(datetime.utcnow().timestamp())}"

        create_kwargs: dict[str, Any] = {}
        if kwargs.get("workspace_id") is not None:
            create_kwargs["workspace_id"] = kwargs["workspace_id"]

        instance = MobileAppInstance(
            id=instance_id,
            name=name,
            description=description,
            enabled=kwargs.get("enabled", True),
            owner_id=kwargs.get("owner_id"),
            **create_kwargs,
            # AI
            llm_backend=kwargs.get("llm_backend", DEFAULT_MOBILE_CONFIG["llm_backend"]),
            llm_persona=kwargs.get("llm_persona", DEFAULT_MOBILE_CONFIG["llm_persona"]),
            system_prompt=kwargs.get("system_prompt"),
            # TTS
            tts_engine=kwargs.get("tts_engine", DEFAULT_MOBILE_CONFIG["tts_engine"]),
            tts_voice=kwargs.get("tts_voice", DEFAULT_MOBILE_CONFIG["tts_voice"]),
            tts_preset=kwargs.get("tts_preset"),
            # RAG
            rag_mode=kwargs.get("rag_mode", "all"),
            # Rate limiting
            rate_limit_count=kwargs.get("rate_limit_count"),
            rate_limit_hours=kwargs.get("rate_limit_hours"),
            # Timestamps
            created=datetime.utcnow(),
            updated=datetime.utcnow(),
        )

        if kwargs.get("llm_params"):
            instance.set_llm_params(kwargs["llm_params"])
        if kwargs.get("knowledge_collection_ids"):
            instance.knowledge_collection_ids = json.dumps(kwargs["knowledge_collection_ids"])

        self.session.add(instance)
        await self.session.flush()

        logger.info(f"Created mobile app instance: {instance_id}")
        return instance.to_dict()

    async def update_instance(self, instance_id: str, **kwargs: Any) -> Optional[dict]:
        instance = await self.session.get(MobileAppInstance, instance_id)
        if not instance:
            return None

        simple_fields = [
            "name",
            "description",
            "enabled",
            "llm_backend",
            "llm_persona",
            "system_prompt",
            "tts_engine",
            "tts_voice",
            "tts_preset",
            "rag_mode",
            "rate_limit_count",
            "rate_limit_hours",
        ]
        for field in simple_fields:
            if field in kwargs:
                setattr(instance, field, kwargs[field])

        if "llm_params" in kwargs:
            if kwargs["llm_params"]:
                instance.set_llm_params(kwargs["llm_params"])
            else:
                instance.llm_params = None
        if "knowledge_collection_ids" in kwargs:
            ids = kwargs["knowledge_collection_ids"]
            instance.knowledge_collection_ids = json.dumps(ids) if ids else None

        instance.updated = datetime.utcnow()
        await self.session.flush()

        logger.info(f"Updated mobile app instance: {instance_id}")
        data: dict[str, Any] = instance.to_dict()
        return data

    async def delete_instance(
        self,
        instance_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> bool:
        query = select(MobileAppInstance).where(MobileAppInstance.id == instance_id)
        if owner_id is not None:
            query = query.where(
                (MobileAppInstance.owner_id == owner_id) | (MobileAppInstance.owner_id.is_(None))
            )
        if workspace_id is not None:
            query = query.where(MobileAppInstance.workspace_id == workspace_id)
        result = await self.session.execute(query)
        instance = result.scalar_one_or_none()
        if not instance:
            return False

        await self.session.delete(instance)
        await self.session.flush()

        logger.info(f"Deleted mobile app instance: {instance_id}")
        return True

    async def set_enabled(self, instance_id: str, enabled: bool) -> bool:
        result = await self.session.execute(
            update(MobileAppInstance)
            .where(MobileAppInstance.id == instance_id)
            .values(enabled=enabled, updated=datetime.utcnow())
        )
        await self.session.flush()
        return bool(result.rowcount > 0)  # type: ignore[attr-defined]

    async def get_enabled_instances(self) -> List[dict]:
        return await self.list_instances(enabled_only=True)

    async def instance_exists(self, instance_id: str) -> bool:
        instance = await self.session.get(MobileAppInstance, instance_id)
        return instance is not None

    async def get_instance_count(self) -> int:
        return await self.count()

    async def get_user_instance(self, user_id: int) -> Optional[dict]:
        """Get the mobile instance assigned to a user (via ResourceShare)."""
        # Find the first mobile_app_instance shared with this user
        share_query = (
            select(ResourceShare.resource_id)
            .where(
                ResourceShare.resource_type == "mobile_app_instance",
                ResourceShare.user_id == user_id,
            )
            .limit(1)
        )
        share_result = await self.session.execute(share_query)
        resource_id = share_result.scalar_one_or_none()
        if not resource_id:
            return None

        instance = await self.session.get(MobileAppInstance, resource_id)
        if not instance or not instance.enabled:
            return None
        return instance.to_dict()

    async def list_user_instances(self, user_id: int) -> List[dict]:
        """List all enabled mobile instances shared with a user via ResourceShare."""
        query = (
            select(MobileAppInstance)
            .join(
                ResourceShare,
                ResourceShare.resource_id == MobileAppInstance.id,
            )
            .where(
                ResourceShare.resource_type == "mobile_app_instance",
                ResourceShare.user_id == user_id,
                MobileAppInstance.enabled.is_(True),
            )
            .order_by(ResourceShare.shared_at.asc())
        )
        result = await self.session.execute(query)
        return [i.to_dict() for i in result.scalars().all()]
