"""Knowledge services."""

import logging
from typing import List, Optional

from db.database import AsyncSessionLocal
from db.repositories import (
    FAQRepository,
    GitHubRepoProjectRepository,
    KnowledgeCollectionRepository,
    KnowledgeDocumentRepository,
)


logger = logging.getLogger(__name__)


class FAQService:
    """Async FAQ manager using database with caching."""

    async def get_all(self, workspace_id: Optional[int] = None) -> dict[str, str]:
        """Get all FAQ as question->answer dict."""
        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)
            return await repo.get_as_dict(workspace_id=workspace_id)

    async def get_all_entries(self, workspace_id: Optional[int] = None) -> List[dict]:
        """Get all FAQ entries with full details."""
        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)
            return await repo.get_all_entries(enabled_only=False, workspace_id=workspace_id)

    async def find_answer(self, question: str) -> Optional[str]:
        """Find exact match answer for question."""
        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)
            return await repo.find_answer(question)

    async def add(self, question: str, answer: str, workspace_id: Optional[int] = None) -> dict:
        """Add new FAQ entry."""
        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)
            result = await repo.create_entry(question, answer, workspace_id=workspace_id)
            await session.commit()
            return result

    async def update(
        self,
        old_question: str,
        question: str,
        answer: str,
        workspace_id: Optional[int] = None,
    ) -> Optional[dict]:
        """Update FAQ entry."""
        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)

            # If question changed, need to find by old and delete + create
            if old_question != question:
                existing = await repo.get_by_question(old_question)
                if existing:
                    await repo.delete_by_question(old_question)
                result = await repo.create_entry(question, answer, workspace_id=workspace_id)
                await session.commit()
                return result
            else:
                existing = await repo.get_by_question(question)
                if existing:
                    result = await repo.update_entry(
                        existing["id"],
                        question=question,
                        answer=answer,
                    )
                    await session.commit()
                    return result
            return None

    async def delete(self, question: str, workspace_id: Optional[int] = None) -> bool:
        """Delete FAQ entry."""
        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)
            result = await repo.delete_by_question(question, workspace_id=workspace_id)
            await session.commit()
            return result

    async def search(self, query: str, workspace_id: Optional[int] = None) -> List[dict]:
        """Search FAQ entries."""
        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)
            return await repo.search(query, workspace_id=workspace_id)


class KnowledgeDocService:
    """Async wrapper for KnowledgeDocumentRepository."""

    async def get_all(self, workspace_id: Optional[int] = None) -> List[dict]:
        """Get all knowledge documents."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeDocumentRepository(session)
            return await repo.get_all_documents(workspace_id=workspace_id)

    async def get_by_id(self, doc_id: int, workspace_id: Optional[int] = None) -> Optional[dict]:
        """Get document by ID, with optional workspace gate-check."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeDocumentRepository(session)
            doc = await repo.get_by_id_ws(doc_id, workspace_id)
            return doc.to_dict() if doc else None

    async def get_by_filename(self, filename: str) -> Optional[dict]:
        """Get document by filename."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeDocumentRepository(session)
            doc = await repo.get_by_filename(filename)
            return doc.to_dict() if doc else None

    async def get_by_collection(
        self, collection_id: int, workspace_id: Optional[int] = None
    ) -> List[dict]:
        """Get all documents in a specific collection."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeDocumentRepository(session)
            return await repo.get_by_collection(collection_id, workspace_id=workspace_id)

    async def create(
        self,
        filename: str,
        title: str,
        source_type: str = "manual",
        file_size_bytes: int = 0,
        section_count: int = 0,
        owner_id: Optional[int] = None,
        collection_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> dict:
        """Create a knowledge document record."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeDocumentRepository(session)
            result = await repo.create_document(
                filename=filename,
                title=title,
                source_type=source_type,
                file_size_bytes=file_size_bytes,
                section_count=section_count,
                owner_id=owner_id,
                collection_id=collection_id,
                workspace_id=workspace_id,
            )
            await session.commit()
            return result

    async def update(
        self,
        doc_id: int,
        title: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        section_count: Optional[int] = None,
        collection_id: Optional[int] = None,
    ) -> Optional[dict]:
        """Update document metadata."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeDocumentRepository(session)
            result = await repo.update_document(
                doc_id, title, file_size_bytes, section_count, collection_id
            )
            await session.commit()
            return result

    async def delete(self, doc_id: int) -> bool:
        """Delete document record."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeDocumentRepository(session)
            result = await repo.delete_document(doc_id)
            await session.commit()
            return result


class KnowledgeCollectionService:
    """Async wrapper for KnowledgeCollectionRepository."""

    async def get_all(
        self, enabled_only: bool = False, workspace_id: Optional[int] = None
    ) -> List[dict]:
        """Get all collections."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeCollectionRepository(session)
            return await repo.get_all_collections(
                enabled_only=enabled_only, workspace_id=workspace_id
            )

    async def get_by_id(
        self, collection_id: int, workspace_id: Optional[int] = None
    ) -> Optional[dict]:
        """Get collection by ID with document count and optional workspace gate-check."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeCollectionRepository(session)
            col = await repo.get_by_id_ws(collection_id, workspace_id)
            if not col:
                return None
            d = col.to_dict()
            # Add document count (lazy import to avoid circular dependency)
            from sqlalchemy import func
            from sqlalchemy import select as sa_select

            from db.models import KnowledgeDocument

            result = await session.execute(
                sa_select(func.count())
                .select_from(KnowledgeDocument)
                .where(KnowledgeDocument.collection_id == collection_id)
            )
            d["document_count"] = result.scalar() or 0
            return d

    async def get_by_slug(self, slug: str) -> Optional[dict]:
        """Get collection by slug with document count."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeCollectionRepository(session)
            col = await repo.get_by_slug(slug)
            if not col:
                return None
            d = col.to_dict()
            from sqlalchemy import func
            from sqlalchemy import select as sa_select

            from db.models import KnowledgeDocument

            result = await session.execute(
                sa_select(func.count())
                .select_from(KnowledgeDocument)
                .where(KnowledgeDocument.collection_id == col.id)
            )
            d["document_count"] = result.scalar() or 0
            return d

    async def get_default(self) -> Optional[dict]:
        """Get the default collection."""
        return await self.get_by_slug("default")

    async def create(
        self,
        name: str,
        slug: str,
        description: Optional[str] = None,
        enabled: bool = True,
        base_dir: str = "wiki-pages",
        workspace_id: Optional[int] = None,
    ) -> dict:
        """Create a collection."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeCollectionRepository(session)
            result = await repo.create_collection(
                name=name,
                slug=slug,
                description=description,
                enabled=enabled,
                base_dir=base_dir,
                workspace_id=workspace_id,
            )
            await session.commit()
            return result

    async def update(
        self,
        collection_id: int,
        name: Optional[str] = None,
        slug: Optional[str] = None,
        description: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[dict]:
        """Update collection metadata."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeCollectionRepository(session)
            result = await repo.update_collection(collection_id, name, slug, description, enabled)
            await session.commit()
            return result

    async def delete(self, collection_id: int) -> bool:
        """Delete collection (orphans documents)."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeCollectionRepository(session)
            result = await repo.delete_collection(collection_id)
            await session.commit()
            return result

    async def get_document_filenames(self, collection_id: int) -> List[str]:
        """Get filenames of all documents in a collection."""
        async with AsyncSessionLocal() as session:
            repo = KnowledgeCollectionRepository(session)
            return await repo.get_document_filenames(collection_id)

    async def ensure_default_exists(self) -> dict:
        """Create default collection if it doesn't exist."""
        default = await self.get_default()
        if default:
            return default
        return await self.create(
            name="Default",
            slug="default",
            description="\u041a\u043e\u043b\u043b\u0435\u043a\u0446\u0438\u044f \u043f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e",
            enabled=True,
        )


class GitHubRepoProjectService:
    """Async wrapper for GitHub repo project repository."""

    async def list_projects(self, workspace_id: Optional[int] = None) -> list[dict]:
        async with AsyncSessionLocal() as session:
            repo = GitHubRepoProjectRepository(session)
            return await repo.list_projects(workspace_id)

    async def get_project(
        self, project_id: int, workspace_id: Optional[int] = None
    ) -> Optional["GitHubRepoProject"]:  # noqa: F821
        async with AsyncSessionLocal() as session:
            repo = GitHubRepoProjectRepository(session)
            return await repo.get_project(project_id, workspace_id)

    async def get_by_repo(self, owner: str, repo_name: str) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = GitHubRepoProjectRepository(session)
            project = await repo.get_by_repo(owner, repo_name)
            return project.to_dict() if project else None

    async def create_project(self, **kwargs) -> dict:
        async with AsyncSessionLocal() as session:
            repo = GitHubRepoProjectRepository(session)
            project = await repo.create_project(**kwargs)
            await session.commit()
            return project.to_dict()

    async def update_project(
        self, project_id: int, workspace_id: Optional[int] = None, **kwargs
    ) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = GitHubRepoProjectRepository(session)
            result = await repo.update_project(project_id, workspace_id, **kwargs)
            await session.commit()
            return result

    async def update_sync_status(
        self,
        project_id: int,
        status: str,
        error: Optional[str] = None,
        commit_sha: Optional[str] = None,
        file_count: Optional[int] = None,
        total_size: Optional[int] = None,
    ) -> None:
        async with AsyncSessionLocal() as session:
            repo = GitHubRepoProjectRepository(session)
            await repo.update_sync_status(
                project_id, status, error, commit_sha, file_count, total_size
            )
            await session.commit()

    async def delete_project(self, project_id: int, workspace_id: Optional[int] = None) -> bool:
        async with AsyncSessionLocal() as session:
            repo = GitHubRepoProjectRepository(session)
            result = await repo.delete_project(project_id, workspace_id)
            await session.commit()
            return result
