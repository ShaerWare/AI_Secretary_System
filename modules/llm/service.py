"""LLM services."""

import logging
from typing import Any, List, Optional

from db.database import AsyncSessionLocal
from db.repositories import CloudProviderRepository


logger = logging.getLogger(__name__)


class CloudProviderService:
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
            result = await repo.create_provider(name, provider_type, **kwargs)
            await session.commit()
            return result

    async def update_provider(self, provider_id: str, **kwargs: Any) -> Optional[dict]:
        """Update cloud provider."""
        async with AsyncSessionLocal() as session:
            repo = CloudProviderRepository(session)
            result = await repo.update_provider(provider_id, **kwargs)
            await session.commit()
            return result

    async def delete_provider(
        self,
        provider_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> bool:
        """Delete cloud provider."""
        async with AsyncSessionLocal() as session:
            repo = CloudProviderRepository(session)
            result = await repo.delete_provider(
                provider_id, owner_id=owner_id, workspace_id=workspace_id
            )
            await session.commit()
            return result

    async def set_default(self, provider_id: str) -> bool:
        """Set provider as default."""
        async with AsyncSessionLocal() as session:
            repo = CloudProviderRepository(session)
            result = await repo.set_default(provider_id)
            await session.commit()
            return result

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
