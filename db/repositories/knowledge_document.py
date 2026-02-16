"""
Repository for knowledge base documents.
"""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import KnowledgeDocument
from db.repositories.base import BaseRepository


class KnowledgeDocumentRepository(BaseRepository[KnowledgeDocument]):
    """Repository for knowledge base document tracking."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, KnowledgeDocument)

    async def get_by_filename(self, filename: str) -> Optional[KnowledgeDocument]:
        """Get document by filename."""
        result = await self.session.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.filename == filename)
        )
        return result.scalar_one_or_none()

    async def get_all_documents(self) -> List[dict]:
        """Get all documents ordered by title."""
        result = await self.session.execute(
            select(KnowledgeDocument).order_by(KnowledgeDocument.title)
        )
        return [doc.to_dict() for doc in result.scalars().all()]

    async def get_by_collection(self, collection_id: int) -> List[dict]:
        """Get all documents in a specific collection."""
        result = await self.session.execute(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.collection_id == collection_id)
            .order_by(KnowledgeDocument.title)
        )
        return [doc.to_dict() for doc in result.scalars().all()]

    async def get_filenames_by_collection(self, collection_id: int) -> List[str]:
        """Get filenames of all documents in a collection."""
        result = await self.session.execute(
            select(KnowledgeDocument.filename).where(
                KnowledgeDocument.collection_id == collection_id
            )
        )
        return [row[0] for row in result.all()]

    async def create_document(
        self,
        filename: str,
        title: str,
        source_type: str = "manual",
        file_size_bytes: int = 0,
        section_count: int = 0,
        owner_id: Optional[int] = None,
        collection_id: Optional[int] = None,
    ) -> dict:
        """Create a new document record."""
        doc = KnowledgeDocument(
            filename=filename,
            title=title,
            source_type=source_type,
            file_size_bytes=file_size_bytes,
            section_count=section_count,
            owner_id=owner_id,
            collection_id=collection_id,
        )
        self.session.add(doc)
        await self.session.commit()
        await self.session.refresh(doc)
        return doc.to_dict()

    async def update_document(
        self,
        doc_id: int,
        title: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        section_count: Optional[int] = None,
        collection_id: Optional[int] = None,
    ) -> Optional[dict]:
        """Update document metadata."""
        doc = await self.session.get(KnowledgeDocument, doc_id)
        if not doc:
            return None

        if title is not None:
            doc.title = title
        if file_size_bytes is not None:
            doc.file_size_bytes = file_size_bytes
        if section_count is not None:
            doc.section_count = section_count
        if collection_id is not None:
            doc.collection_id = collection_id

        await self.session.commit()
        await self.session.refresh(doc)
        return doc.to_dict()

    async def delete_document(self, doc_id: int) -> bool:
        """Delete document by ID."""
        doc = await self.session.get(KnowledgeDocument, doc_id)
        if not doc:
            return False
        await self.session.delete(doc)
        await self.session.commit()
        return True
