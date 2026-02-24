"""
Repository for knowledge base collections.
"""

from typing import Any, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import KnowledgeCollection, KnowledgeDocument
from db.repositories.base import BaseRepository


class KnowledgeCollectionRepository(BaseRepository[KnowledgeCollection]):
    """Repository for knowledge base collections."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, KnowledgeCollection)

    async def get_by_slug(self, slug: str) -> Optional[KnowledgeCollection]:
        """Get collection by slug with loaded documents."""
        result = await self.session.execute(
            select(KnowledgeCollection)
            .where(KnowledgeCollection.slug == slug)
            .options(selectinload(KnowledgeCollection.documents))
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[KnowledgeCollection]:
        """Get collection by name."""
        result = await self.session.execute(
            select(KnowledgeCollection).where(KnowledgeCollection.name == name)
        )
        return result.scalar_one_or_none()

    async def get_all_collections(
        self, enabled_only: bool = False, workspace_id: Optional[int] = None
    ) -> List[dict]:
        """Get all collections ordered by name, with document count."""
        stmt = (
            select(
                KnowledgeCollection,
                func.count(KnowledgeDocument.id).label("document_count"),
            )
            .outerjoin(KnowledgeDocument)
            .group_by(KnowledgeCollection.id)
            .order_by(KnowledgeCollection.name)
        )
        if enabled_only:
            stmt = stmt.where(KnowledgeCollection.enabled.is_(True))
        if workspace_id is not None and hasattr(KnowledgeCollection, "workspace_id"):
            stmt = stmt.where(KnowledgeCollection.workspace_id == workspace_id)

        result = await self.session.execute(stmt)
        collections = []
        for row in result.all():
            col = row[0]
            doc_count = row[1]
            d = {
                "id": col.id,
                "name": col.name,
                "slug": col.slug,
                "description": col.description,
                "enabled": col.enabled,
                "base_dir": col.base_dir,
                "document_count": doc_count,
                "created": col.created.isoformat() if col.created else None,
                "updated": col.updated.isoformat() if col.updated else None,
            }
            collections.append(d)
        return collections

    async def create_collection(
        self,
        name: str,
        slug: str,
        description: Optional[str] = None,
        enabled: bool = True,
        base_dir: str = "wiki-pages",
        workspace_id: Optional[int] = None,
    ) -> dict:
        """Create a new collection."""
        create_kwargs: dict[str, Any] = {}
        if workspace_id is not None:
            create_kwargs["workspace_id"] = workspace_id

        col = KnowledgeCollection(
            name=name,
            slug=slug,
            description=description,
            enabled=enabled,
            base_dir=base_dir,
            **create_kwargs,
        )
        self.session.add(col)
        await self.session.commit()
        await self.session.refresh(col)
        d = col.to_dict()
        d["document_count"] = 0
        return d

    async def update_collection(
        self,
        collection_id: int,
        name: Optional[str] = None,
        slug: Optional[str] = None,
        description: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[dict]:
        """Update collection metadata."""
        col = await self.session.get(KnowledgeCollection, collection_id)
        if not col:
            return None

        if name is not None:
            col.name = name
        if slug is not None:
            col.slug = slug
        if description is not None:
            col.description = description
        if enabled is not None:
            col.enabled = enabled

        await self.session.commit()
        await self.session.refresh(col)
        d = col.to_dict()
        # Count documents
        result = await self.session.execute(
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(KnowledgeDocument.collection_id == collection_id)
        )
        d["document_count"] = result.scalar() or 0
        return d

    async def delete_collection(self, collection_id: int) -> bool:
        """Delete collection. Sets orphaned docs' collection_id to NULL."""
        col = await self.session.get(KnowledgeCollection, collection_id)
        if not col:
            return False

        # Orphan documents
        result = await self.session.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.collection_id == collection_id)
        )
        for doc in result.scalars().all():
            doc.collection_id = None

        await self.session.delete(col)
        await self.session.commit()
        return True

    async def get_document_filenames(self, collection_id: int) -> List[str]:
        """Get filenames of all documents in a collection."""
        result = await self.session.execute(
            select(KnowledgeDocument.filename).where(
                KnowledgeDocument.collection_id == collection_id
            )
        )
        return [row[0] for row in result.all()]
