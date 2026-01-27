"""
Cloud LLM provider repository for managing cloud provider configurations.
"""

import logging
import re
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import CloudLLMProvider
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:50]


class CloudProviderRepository(BaseRepository[CloudLLMProvider]):
    """Repository for cloud LLM providers."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, CloudLLMProvider)

    def _generate_id(self, name: str, provider_type: str) -> str:
        """Generate unique ID from name and type."""
        base = slugify(f"{provider_type}-{name}")
        return base or f"provider-{int(datetime.utcnow().timestamp())}"

    async def list_providers(self, enabled_only: bool = False) -> List[dict]:
        """List all providers."""
        query = select(CloudLLMProvider).order_by(CloudLLMProvider.updated.desc())
        if enabled_only:
            query = query.where(CloudLLMProvider.enabled == True)

        result = await self.session.execute(query)
        providers = result.scalars().all()
        return [p.to_dict() for p in providers]

    async def get_provider(self, provider_id: str) -> Optional[dict]:
        """Get provider by ID (without API key)."""
        provider = await self.session.get(CloudLLMProvider, provider_id)
        return provider.to_dict() if provider else None

    async def get_provider_with_key(self, provider_id: str) -> Optional[dict]:
        """Get provider with API key (for internal use)."""
        provider = await self.session.get(CloudLLMProvider, provider_id)
        return provider.to_dict(include_key=True) if provider else None

    async def get_default_provider(self) -> Optional[dict]:
        """Get the default cloud provider."""
        result = await self.session.execute(
            select(CloudLLMProvider)
            .where(CloudLLMProvider.is_default == True)
            .where(CloudLLMProvider.enabled == True)
        )
        provider = result.scalar_one_or_none()
        return provider.to_dict(include_key=True) if provider else None

    async def get_first_enabled(self) -> Optional[dict]:
        """Get first enabled provider (fallback if no default)."""
        result = await self.session.execute(
            select(CloudLLMProvider)
            .where(CloudLLMProvider.enabled == True)
            .order_by(CloudLLMProvider.updated.desc())
            .limit(1)
        )
        provider = result.scalar_one_or_none()
        return provider.to_dict(include_key=True) if provider else None

    async def create_provider(
        self,
        name: str,
        provider_type: str,
        api_key: str = None,
        base_url: str = None,
        model_name: str = "",
        **kwargs,
    ) -> dict:
        """Create new provider."""
        provider_id = kwargs.pop("id", None) or self._generate_id(name, provider_type)

        # Check if ID exists
        existing = await self.session.get(CloudLLMProvider, provider_id)
        if existing:
            provider_id = f"{provider_id}-{int(datetime.utcnow().timestamp())}"

        # If this is set as default, unset others
        if kwargs.get("is_default", False):
            await self._unset_all_defaults()

        provider = CloudLLMProvider(
            id=provider_id,
            name=name,
            provider_type=provider_type,
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            enabled=kwargs.get("enabled", True),
            is_default=kwargs.get("is_default", False),
            description=kwargs.get("description"),
            created=datetime.utcnow(),
            updated=datetime.utcnow(),
        )

        if kwargs.get("config"):
            provider.set_config(kwargs["config"])

        self.session.add(provider)
        await self.session.commit()
        await self.session.refresh(provider)

        logger.info(f"Created cloud provider: {provider_id}")
        return provider.to_dict()

    async def update_provider(self, provider_id: str, **kwargs) -> Optional[dict]:
        """Update provider."""
        provider = await self.session.get(CloudLLMProvider, provider_id)
        if not provider:
            return None

        # If setting as default, unset others
        if kwargs.get("is_default", False) and not provider.is_default:
            await self._unset_all_defaults()

        # Update simple fields
        simple_fields = [
            "name",
            "provider_type",
            "api_key",
            "base_url",
            "model_name",
            "enabled",
            "is_default",
            "description",
        ]
        for field in simple_fields:
            if field in kwargs and kwargs[field] is not None:
                # Don't update api_key if empty string
                if field == "api_key" and kwargs[field] == "":
                    continue
                setattr(provider, field, kwargs[field])

        # Update JSON config
        if "config" in kwargs and kwargs["config"] is not None:
            provider.set_config(kwargs["config"])

        provider.updated = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(provider)

        logger.info(f"Updated cloud provider: {provider_id}")
        return provider.to_dict()

    async def delete_provider(self, provider_id: str) -> bool:
        """Delete provider."""
        provider = await self.session.get(CloudLLMProvider, provider_id)
        if not provider:
            return False

        await self.session.delete(provider)
        await self.session.commit()

        logger.info(f"Deleted cloud provider: {provider_id}")
        return True

    async def set_default(self, provider_id: str) -> bool:
        """Set provider as default."""
        # Check if provider exists and is enabled
        provider = await self.session.get(CloudLLMProvider, provider_id)
        if not provider or not provider.enabled:
            return False

        await self._unset_all_defaults()

        result = await self.session.execute(
            update(CloudLLMProvider)
            .where(CloudLLMProvider.id == provider_id)
            .values(is_default=True, updated=datetime.utcnow())
        )
        await self.session.commit()
        return result.rowcount > 0

    async def _unset_all_defaults(self):
        """Unset all default flags."""
        await self.session.execute(
            update(CloudLLMProvider)
            .where(CloudLLMProvider.is_default == True)
            .values(is_default=False)
        )

    async def get_by_type(self, provider_type: str, enabled_only: bool = True) -> List[dict]:
        """Get providers by type."""
        query = select(CloudLLMProvider).where(CloudLLMProvider.provider_type == provider_type)
        if enabled_only:
            query = query.where(CloudLLMProvider.enabled == True)

        result = await self.session.execute(query)
        providers = result.scalars().all()
        return [p.to_dict() for p in providers]

    async def provider_exists(self, provider_id: str) -> bool:
        """Check if provider exists."""
        provider = await self.session.get(CloudLLMProvider, provider_id)
        return provider is not None

    async def get_provider_count(self) -> int:
        """Get total number of providers."""
        return await self.count()
