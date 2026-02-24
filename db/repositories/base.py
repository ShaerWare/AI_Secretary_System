"""
Base repository class with common database operations.
"""

from typing import Any, Generic, List, Optional, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase


T = TypeVar("T", bound=DeclarativeBase)


class BaseRepository(Generic[T]):
    """Base repository with common CRUD operations."""

    def __init__(self, session: AsyncSession, model: Type[T]):
        self.session = session
        self.model = model

    def _apply_workspace_filter(self, query, workspace_id: Optional[int]):
        """Add WHERE workspace_id = :workspace_id if model supports it.

        Pass workspace_id=None to skip filtering (backward compatible).
        """
        if workspace_id is not None and hasattr(self.model, "workspace_id"):
            query = query.where(self.model.workspace_id == workspace_id)
        return query

    async def get_by_id(self, id_value: Any) -> Optional[T]:
        """Get entity by primary key."""
        result: Optional[T] = await self.session.get(self.model, id_value)
        return result

    async def get_by_id_ws(self, id_value: Any, workspace_id: Optional[int] = None) -> Optional[T]:
        """Get entity by PK with optional workspace filter.

        Gate-check for mutation endpoints: returns None if the entity
        exists but belongs to a different workspace.
        """
        if workspace_id is None:
            return await self.get_by_id(id_value)
        query = select(self.model).where(self.model.id == id_value)
        query = self._apply_workspace_filter(query, workspace_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_all(self, limit: int = 1000, offset: int = 0) -> List[T]:
        """Get all entities with pagination."""
        result = await self.session.execute(select(self.model).limit(limit).offset(offset))
        return list(result.scalars().all())

    async def create(self, entity: T) -> T:
        """Create new entity."""
        self.session.add(entity)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity

    async def update(self, entity: T) -> T:
        """Update existing entity."""
        await self.session.commit()
        await self.session.refresh(entity)
        return entity

    async def delete(self, entity: T) -> bool:
        """Delete entity."""
        await self.session.delete(entity)
        await self.session.commit()
        return True

    async def delete_by_id(self, id_value: Any) -> bool:
        """Delete entity by primary key."""
        entity = await self.get_by_id(id_value)
        if entity:
            await self.delete(entity)
            return True
        return False

    async def count(self) -> int:
        """Count all entities."""
        from sqlalchemy import func

        result = await self.session.execute(select(func.count()).select_from(self.model))
        return result.scalar() or 0

    async def exists(self, id_value: Any) -> bool:
        """Check if entity exists by primary key."""
        entity = await self.get_by_id(id_value)
        return entity is not None
