"""Mobile app channel services."""

import logging
from typing import Any, List, Optional

from db.database import AsyncSessionLocal
from db.repositories.mobile_app_instance import MobileAppInstanceRepository


logger = logging.getLogger(__name__)


class MobileAppInstanceService:
    """Async manager for mobile app instances."""

    async def list_instances(
        self,
        enabled_only: bool = False,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> List[dict]:
        async with AsyncSessionLocal() as session:
            repo = MobileAppInstanceRepository(session)
            return await repo.list_instances(
                enabled_only=enabled_only, owner_id=owner_id, workspace_id=workspace_id
            )

    async def get_instance(
        self,
        instance_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = MobileAppInstanceRepository(session)
            return await repo.get_instance(
                instance_id, owner_id=owner_id, workspace_id=workspace_id
            )

    async def create_instance(self, name: str, **kwargs: Any) -> dict:
        async with AsyncSessionLocal() as session:
            repo = MobileAppInstanceRepository(session)
            result = await repo.create_instance(name, **kwargs)
            await session.commit()
            return result

    async def update_instance(self, instance_id: str, **kwargs: Any) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = MobileAppInstanceRepository(session)
            result = await repo.update_instance(instance_id, **kwargs)
            await session.commit()
            return result

    async def delete_instance(
        self,
        instance_id: str,
        owner_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> bool:
        async with AsyncSessionLocal() as session:
            repo = MobileAppInstanceRepository(session)
            result = await repo.delete_instance(
                instance_id, owner_id=owner_id, workspace_id=workspace_id
            )
            await session.commit()
            return result

    async def set_enabled(self, instance_id: str, enabled: bool) -> bool:
        async with AsyncSessionLocal() as session:
            repo = MobileAppInstanceRepository(session)
            result = await repo.set_enabled(instance_id, enabled)
            await session.commit()
            return result

    async def get_enabled_instances(self) -> List[dict]:
        async with AsyncSessionLocal() as session:
            repo = MobileAppInstanceRepository(session)
            return await repo.get_enabled_instances()

    async def instance_exists(self, instance_id: str) -> bool:
        async with AsyncSessionLocal() as session:
            repo = MobileAppInstanceRepository(session)
            return await repo.instance_exists(instance_id)

    async def get_instance_count(self) -> int:
        async with AsyncSessionLocal() as session:
            repo = MobileAppInstanceRepository(session)
            return await repo.get_instance_count()

    async def get_user_instance(self, user_id: int) -> Optional[dict]:
        """Get the mobile instance assigned to a specific user."""
        async with AsyncSessionLocal() as session:
            repo = MobileAppInstanceRepository(session)
            return await repo.get_user_instance(user_id)


# Singleton
mobile_app_instance_service = MobileAppInstanceService()
