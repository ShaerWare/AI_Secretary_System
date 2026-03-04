"""Widget channel services."""

import logging
from typing import Any, List, Optional

from db.database import AsyncSessionLocal
from db.repositories import WidgetInstanceRepository


logger = logging.getLogger(__name__)


class WidgetInstanceService:
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
            result = await repo.create_instance(name, **kwargs)
            await session.commit()
            return result

    async def update_instance(self, instance_id: str, **kwargs: Any) -> Optional[dict]:
        """Update widget instance."""
        async with AsyncSessionLocal() as session:
            repo = WidgetInstanceRepository(session)
            result = await repo.update_instance(instance_id, **kwargs)
            await session.commit()
            return result

    async def delete_instance(
        self,
        instance_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> bool:
        """Delete widget instance."""
        async with AsyncSessionLocal() as session:
            repo = WidgetInstanceRepository(session)
            result = await repo.delete_instance(
                instance_id, owner_id=owner_id, workspace_id=workspace_id
            )
            await session.commit()
            return result

    async def set_enabled(self, instance_id: str, enabled: bool) -> bool:
        """Enable or disable widget instance."""
        async with AsyncSessionLocal() as session:
            repo = WidgetInstanceRepository(session)
            result = await repo.set_enabled(instance_id, enabled)
            await session.commit()
            return result

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
            result = await repo.import_from_legacy_config(config, instance_id)
            await session.commit()
            return result


# Singleton
widget_instance_service = WidgetInstanceService()
