"""Repository for RBAC roles and permissions."""

from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Role, RolePermission
from db.repositories.base import BaseRepository


class RoleRepository(BaseRepository[Role]):
    """Repository for roles with permission management."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Role)

    async def get_by_name(self, name: str) -> Optional[Role]:
        """Get a role by its unique name, with permissions eagerly loaded."""
        result = await self.session.execute(
            select(Role).where(Role.name == name).options(selectinload(Role.permissions))
        )
        return result.scalar_one_or_none()

    async def get_with_permissions(self, role_id: int) -> Optional[Role]:
        """Get a role by ID with permissions eagerly loaded."""
        result = await self.session.execute(
            select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
        )
        return result.scalar_one_or_none()

    async def get_all_with_permissions(self) -> List[Role]:
        """Get all roles with permissions eagerly loaded."""
        result = await self.session.execute(
            select(Role).options(selectinload(Role.permissions)).order_by(Role.id)
        )
        return list(result.scalars().all())

    async def create_role(
        self,
        name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        is_system: bool = False,
        permissions: Optional[Dict[str, str]] = None,
    ) -> Role:
        """Create a new role with optional permissions dict {module: level}."""
        role = Role(
            name=name,
            display_name=display_name,
            description=description,
            is_system=is_system,
        )
        if permissions:
            role.permissions = [
                RolePermission(module=module, level=level)
                for module, level in permissions.items()
            ]
        self.session.add(role)
        await self.session.commit()
        await self.session.refresh(role)
        return role

    async def update_role(
        self,
        role_id: int,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        permissions: Optional[Dict[str, str]] = None,
    ) -> Optional[Role]:
        """Update role fields and replace permissions if provided."""
        role = await self.get_with_permissions(role_id)
        if not role:
            return None

        if display_name is not None:
            role.display_name = display_name
        if description is not None:
            role.description = description

        if permissions is not None:
            # Replace all permissions
            for perm in list(role.permissions):
                await self.session.delete(perm)
            await self.session.flush()
            role.permissions = [
                RolePermission(role_id=role_id, module=module, level=level)
                for module, level in permissions.items()
            ]

        await self.session.commit()
        return await self.get_with_permissions(role_id)

    async def delete_role(self, role_id: int) -> bool:
        """Delete a non-system role. Returns False if role is system or not found."""
        role = await self.get_by_id(role_id)
        if not role:
            return False
        if role.is_system:
            return False
        await self.session.delete(role)
        await self.session.commit()
        return True
