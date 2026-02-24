"""Repository for kanban project management."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import KanbanProject
from db.repositories.base import BaseRepository


class KanbanProjectRepository(BaseRepository[KanbanProject]):
    """Repository for kanban projects linked to GitHub repos."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, KanbanProject)

    async def get_all_projects(self, workspace_id: Optional[int] = None) -> List[dict]:
        """Get all projects (safe dict, no token exposed)."""
        query = select(KanbanProject).order_by(KanbanProject.name)
        query = self._apply_workspace_filter(query, workspace_id)
        result = await self.session.execute(query)
        return [p.to_dict() for p in result.scalars().all()]

    async def get_project_with_token(self, project_id: int) -> Optional[KanbanProject]:
        """Get project ORM object (includes token for sync operations)."""
        return await self.session.get(KanbanProject, project_id)

    async def get_by_repo(self, owner: str, repo: str) -> Optional[KanbanProject]:
        """Find project by GitHub owner/repo."""
        result = await self.session.execute(
            select(KanbanProject).where(
                KanbanProject.github_owner == owner,
                KanbanProject.github_repo == repo,
            )
        )
        return result.scalar_one_or_none()

    async def create_project(self, **kwargs) -> dict:
        """Create a new project."""
        project = KanbanProject(**kwargs)
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project.to_dict()

    async def update_project(self, project_id: int, **kwargs) -> Optional[dict]:
        """Update project fields."""
        project = await self.session.get(KanbanProject, project_id)
        if not project:
            return None
        for key, value in kwargs.items():
            if hasattr(project, key):
                setattr(project, key, value)
        await self.session.commit()
        await self.session.refresh(project)
        return project.to_dict()

    async def update_last_synced(self, project_id: int) -> None:
        """Update last_synced timestamp."""
        project = await self.session.get(KanbanProject, project_id)
        if project:
            project.last_synced = datetime.utcnow()
            await self.session.commit()
