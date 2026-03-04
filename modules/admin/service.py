"""Admin services."""

import logging
from typing import List, Optional

from db.database import AsyncSessionLocal
from db.repositories import ResourceShareRepository, UserRepository


logger = logging.getLogger(__name__)


class ResourceShareService:
    """Async manager for resource sharing (bot/widget/whatsapp instances) between users."""

    async def get_shares(self, resource_type: str, resource_id: str) -> List[dict]:
        """Get all shares for a resource with user info."""
        async with AsyncSessionLocal() as session:
            repo = ResourceShareRepository(session)
            return await repo.get_shares_for_resource(resource_type, resource_id)

    async def add_share(
        self,
        resource_type: str,
        resource_id: str,
        user_id: int,
        permission: str = "view",
        shared_by: Optional[int] = None,
    ) -> dict:
        """Add or update a share."""
        async with AsyncSessionLocal() as session:
            repo = ResourceShareRepository(session)
            result = await repo.add_share(
                resource_type, resource_id, user_id, permission, shared_by
            )
            await session.commit()
            return result

    async def remove_share(self, resource_type: str, resource_id: str, user_id: int) -> bool:
        """Remove a share."""
        async with AsyncSessionLocal() as session:
            repo = ResourceShareRepository(session)
            result = await repo.remove_share(resource_type, resource_id, user_id)
            await session.commit()
            return result

    async def update_permission(
        self,
        resource_type: str,
        resource_id: str,
        user_id: int,
        permission: str,
    ) -> bool:
        """Update share permission."""
        async with AsyncSessionLocal() as session:
            repo = ResourceShareRepository(session)
            result = await repo.update_permission(resource_type, resource_id, user_id, permission)
            await session.commit()
            return result

    async def get_user_permission(
        self, resource_type: str, resource_id: str, user_id: int
    ) -> Optional[str]:
        """Get user's permission for a resource."""
        async with AsyncSessionLocal() as session:
            repo = ResourceShareRepository(session)
            return await repo.get_user_permission(resource_type, resource_id, user_id)

    async def get_share_counts(self, resource_type: str, resource_ids: list[str]) -> dict[str, int]:
        """Get share counts for multiple resources."""
        async with AsyncSessionLocal() as session:
            repo = ResourceShareRepository(session)
            return await repo.get_share_counts(resource_type, resource_ids)

    async def get_shared_resources_with_permissions(
        self, resource_type: str, user_id: int
    ) -> dict[str, str]:
        """Get dict of resource_id -> permission for resources shared with user."""
        async with AsyncSessionLocal() as session:
            repo = ResourceShareRepository(session)
            return await repo.get_shared_resources_with_permissions(resource_type, user_id)

    async def remove_all_shares(self, resource_type: str, resource_id: str) -> int:
        """Remove all shares for a resource."""
        async with AsyncSessionLocal() as session:
            repo = ResourceShareRepository(session)
            result = await repo.remove_all_shares(resource_type, resource_id)
            await session.commit()
            return result

    async def remove_all_user_shares(self, user_id: int) -> int:
        """Remove all shares for a user (GDPR)."""
        async with AsyncSessionLocal() as session:
            repo = ResourceShareRepository(session)
            result = await repo.remove_all_user_shares(user_id)
            await session.commit()
            return result

    async def list_shareable_users(self, exclude_user_id: Optional[int] = None) -> List[dict]:
        """Get list of active non-guest users for sharing."""
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)
            users = await repo.list_users()
            return [
                {
                    "id": u["id"],
                    "username": u["username"],
                    "display_name": u["display_name"],
                    "role": u["role"],
                }
                for u in users
                if u.get("is_active", True)
                and u.get("role") != "guest"
                and u["id"] != exclude_user_id
            ]


# Singleton
resource_share_service = ResourceShareService()
