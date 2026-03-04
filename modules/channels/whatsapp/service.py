"""WhatsApp channel services."""

import logging
from typing import Any, List, Optional

from db.database import AsyncSessionLocal
from db.repositories import WhatsAppInstanceRepository


logger = logging.getLogger(__name__)


class WhatsAppInstanceService:
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
            result = await repo.create_instance(name, **kwargs)
            await session.commit()
            return result

    async def update_instance(self, instance_id: str, **kwargs: Any) -> Optional[dict]:
        """Update WhatsApp instance."""
        async with AsyncSessionLocal() as session:
            repo = WhatsAppInstanceRepository(session)
            result = await repo.update_instance(instance_id, **kwargs)
            await session.commit()
            return result

    async def delete_instance(
        self,
        instance_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> bool:
        """Delete WhatsApp instance."""
        async with AsyncSessionLocal() as session:
            repo = WhatsAppInstanceRepository(session)
            result = await repo.delete_instance(
                instance_id, owner_id=owner_id, workspace_id=workspace_id
            )
            await session.commit()
            return result

    async def set_enabled(self, instance_id: str, enabled: bool) -> bool:
        """Enable or disable WhatsApp instance."""
        async with AsyncSessionLocal() as session:
            repo = WhatsAppInstanceRepository(session)
            result = await repo.set_enabled(instance_id, enabled)
            await session.commit()
            return result

    async def set_auto_start(self, instance_id: str, auto_start: bool) -> bool:
        """Set auto-start flag for WhatsApp instance."""
        async with AsyncSessionLocal() as session:
            repo = WhatsAppInstanceRepository(session)
            result = await repo.set_auto_start(instance_id, auto_start)
            await session.commit()
            return result

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


# Singleton
whatsapp_instance_service = WhatsAppInstanceService()
