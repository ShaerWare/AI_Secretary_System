"""
Repository for managing resource sharing (bot/widget/whatsapp instances) between users.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ResourceShare, User
from db.repositories.base import BaseRepository


class ResourceShareRepository(BaseRepository[ResourceShare]):
    """Repository for resource share operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ResourceShare)

    async def get_shares_for_resource(self, resource_type: str, resource_id: str) -> List[dict]:
        """Get all shares for a resource with user info."""
        result = await self.session.execute(
            select(ResourceShare, User.username, User.display_name)
            .join(User, ResourceShare.user_id == User.id)
            .where(
                ResourceShare.resource_type == resource_type,
                ResourceShare.resource_id == resource_id,
            )
            .order_by(ResourceShare.shared_at.desc())
        )
        rows = result.all()
        return [
            {
                **share.to_dict(),
                "username": username,
                "display_name": display_name,
            }
            for share, username, display_name in rows
        ]

    async def add_share(
        self,
        resource_type: str,
        resource_id: str,
        user_id: int,
        permission: str = "view",
        shared_by: Optional[int] = None,
    ) -> dict:
        """Add or update a share (upsert)."""
        existing = await self._get_share(resource_type, resource_id, user_id)
        if existing:
            existing.permission = permission
            existing.shared_by = shared_by
            existing.shared_at = datetime.utcnow()
            await self.session.commit()
            return existing.to_dict()

        share = ResourceShare(
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            permission=permission,
            shared_by=shared_by,
            shared_at=datetime.utcnow(),
        )
        self.session.add(share)
        await self.session.flush()
        await self.session.commit()
        return share.to_dict()

    async def remove_share(self, resource_type: str, resource_id: str, user_id: int) -> bool:
        """Remove a share."""
        result = await self.session.execute(
            delete(ResourceShare).where(
                ResourceShare.resource_type == resource_type,
                ResourceShare.resource_id == resource_id,
                ResourceShare.user_id == user_id,
            )
        )
        await self.session.commit()
        return bool(result.rowcount > 0)  # type: ignore[attr-defined]

    async def update_permission(
        self,
        resource_type: str,
        resource_id: str,
        user_id: int,
        permission: str,
    ) -> bool:
        """Update share permission."""
        result = await self.session.execute(
            update(ResourceShare)
            .where(
                ResourceShare.resource_type == resource_type,
                ResourceShare.resource_id == resource_id,
                ResourceShare.user_id == user_id,
            )
            .values(permission=permission)
        )
        await self.session.commit()
        return bool(result.rowcount > 0)  # type: ignore[attr-defined]

    async def remove_all_shares(self, resource_type: str, resource_id: str) -> int:
        """Remove all shares for a resource."""
        result = await self.session.execute(
            delete(ResourceShare).where(
                ResourceShare.resource_type == resource_type,
                ResourceShare.resource_id == resource_id,
            )
        )
        await self.session.commit()
        return int(result.rowcount)  # type: ignore[attr-defined]

    async def get_shared_resource_ids(self, resource_type: str, user_id: int) -> List[str]:
        """Get all resource IDs of a type shared with a user."""
        result = await self.session.execute(
            select(ResourceShare.resource_id).where(
                ResourceShare.resource_type == resource_type,
                ResourceShare.user_id == user_id,
            )
        )
        return [row[0] for row in result.all()]

    async def get_user_permission(
        self, resource_type: str, resource_id: str, user_id: int
    ) -> Optional[str]:
        """Get user's permission for a resource (None if not shared)."""
        result = await self.session.execute(
            select(ResourceShare.permission).where(
                ResourceShare.resource_type == resource_type,
                ResourceShare.resource_id == resource_id,
                ResourceShare.user_id == user_id,
            )
        )
        row = result.first()
        return row[0] if row else None

    async def get_share_counts(self, resource_type: str, resource_ids: list[str]) -> dict[str, int]:
        """Get share counts for multiple resources in a single query."""
        if not resource_ids:
            return {}
        result = await self.session.execute(
            select(ResourceShare.resource_id, func.count())
            .where(
                ResourceShare.resource_type == resource_type,
                ResourceShare.resource_id.in_(resource_ids),
            )
            .group_by(ResourceShare.resource_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def get_shared_resources_with_permissions(
        self, resource_type: str, user_id: int
    ) -> dict[str, str]:
        """Get dict of resource_id -> permission for resources shared with user."""
        result = await self.session.execute(
            select(ResourceShare.resource_id, ResourceShare.permission).where(
                ResourceShare.resource_type == resource_type,
                ResourceShare.user_id == user_id,
            )
        )
        return {row[0]: row[1] for row in result.all()}

    async def remove_all_user_shares(self, user_id: int) -> int:
        """Remove all shares for a user (GDPR deletion)."""
        result = await self.session.execute(
            delete(ResourceShare).where(ResourceShare.user_id == user_id)
        )
        await self.session.commit()
        return int(result.rowcount)  # type: ignore[attr-defined]

    async def _get_share(
        self, resource_type: str, resource_id: str, user_id: int
    ) -> Optional[ResourceShare]:
        """Get a specific share record."""
        result = await self.session.execute(
            select(ResourceShare).where(
                ResourceShare.resource_type == resource_type,
                ResourceShare.resource_id == resource_id,
                ResourceShare.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()
