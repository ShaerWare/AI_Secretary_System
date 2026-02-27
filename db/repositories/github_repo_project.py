"""Repository for GitHub repository projects (knowledge base sync)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import GitHubRepoProject
from db.repositories.base import BaseRepository


class GitHubRepoProjectRepository(BaseRepository[GitHubRepoProject]):
    """Repository for GitHub repo projects linked to knowledge base collections."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, GitHubRepoProject)

    async def list_projects(self, workspace_id: Optional[int] = None) -> list[dict]:
        """Get all projects (safe dict, no token exposed)."""
        query = select(GitHubRepoProject).order_by(GitHubRepoProject.name)
        query = self._apply_workspace_filter(query, workspace_id)
        result = await self.session.execute(query)
        return [p.to_dict() for p in result.scalars().all()]

    async def get_project(
        self, project_id: int, workspace_id: Optional[int] = None
    ) -> Optional[GitHubRepoProject]:
        """Get project ORM object (includes token for sync operations)."""
        if workspace_id is not None:
            query = select(GitHubRepoProject).where(GitHubRepoProject.id == project_id)
            query = self._apply_workspace_filter(query, workspace_id)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        return await self.session.get(GitHubRepoProject, project_id)

    async def get_by_collection_id(self, collection_id: int) -> Optional[GitHubRepoProject]:
        """Find project by linked collection."""
        result = await self.session.execute(
            select(GitHubRepoProject).where(GitHubRepoProject.collection_id == collection_id)
        )
        return result.scalar_one_or_none()

    async def get_by_repo(self, owner: str, repo: str) -> Optional[GitHubRepoProject]:
        """Find project by GitHub owner/repo."""
        result = await self.session.execute(
            select(GitHubRepoProject).where(
                GitHubRepoProject.github_owner == owner,
                GitHubRepoProject.github_repo == repo,
            )
        )
        return result.scalar_one_or_none()

    async def create_project(self, **kwargs) -> GitHubRepoProject:
        """Create a new project. Returns ORM object."""
        project = GitHubRepoProject(**kwargs)
        self.session.add(project)
        await self.session.flush()
        await self.session.commit()
        return project

    async def update_project(
        self, project_id: int, workspace_id: Optional[int] = None, **kwargs
    ) -> Optional[dict]:
        """Update project fields."""
        project = await self.get_project(project_id, workspace_id)
        if not project:
            return None
        for key, value in kwargs.items():
            if hasattr(project, key):
                setattr(project, key, value)
        project.updated = datetime.utcnow()
        await self.session.commit()
        return project.to_dict()

    async def update_sync_status(
        self,
        project_id: int,
        status: str,
        error: Optional[str] = None,
        commit_sha: Optional[str] = None,
        file_count: Optional[int] = None,
        total_size: Optional[int] = None,
    ) -> None:
        """Update sync status fields."""
        project = await self.session.get(GitHubRepoProject, project_id)
        if not project:
            return
        project.sync_status = status
        project.sync_error = error
        if commit_sha is not None:
            project.last_commit_sha = commit_sha
        if status == "idle" and error is None:
            project.last_synced = datetime.utcnow()
        if file_count is not None:
            project.file_count = file_count
        if total_size is not None:
            project.total_size_bytes = total_size
        project.updated = datetime.utcnow()
        await self.session.commit()

    async def delete_project(self, project_id: int, workspace_id: Optional[int] = None) -> bool:
        """Delete a project. Returns True if deleted."""
        project = await self.get_project(project_id, workspace_id)
        if not project:
            return False
        await self.session.delete(project)
        await self.session.commit()
        return True
