"""
Base repository class with common database operations.
"""

from typing import Generic, List, Optional, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase


T = TypeVar("T", bound=DeclarativeBase)


class BaseRepository(Generic[T]):
    """Base repository with common CRUD operations."""

    def __init__(self, session: AsyncSession, model: Type[T]):
        self.session = session
        self.model = model

    async def get_by_id(self, id_value) -> Optional[T]:
        """Get entity by primary key."""
        return await self.session.get(self.model, id_value)

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

    async def delete_by_id(self, id_value) -> bool:
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

    async def exists(self, id_value) -> bool:
        """Check if entity exists by primary key."""
        entity = await self.get_by_id(id_value)
        return entity is not None
