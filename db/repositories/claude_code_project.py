"""Repository for Claude Code projects."""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ClaudeCodeProject
from db.repositories.base import BaseRepository


class ClaudeCodeProjectRepository(BaseRepository[ClaudeCodeProject]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ClaudeCodeProject)

    async def list_projects(
        self,
        owner_id: int,
        workspace_id: Optional[int] = None,
    ) -> List[dict]:
        query = select(ClaudeCodeProject).order_by(ClaudeCodeProject.created.asc())
        query = self._apply_workspace_filter(query, workspace_id)
        query = query.where(ClaudeCodeProject.owner_id == owner_id)
        result = await self.session.execute(query)
        return [p.to_dict() for p in result.scalars().all()]

    async def create_project(
        self,
        name: str,
        path: str,
        owner_id: int,
        type: str = "local",
        ssh_host: Optional[str] = None,
        ssh_user: str = "root",
        ssh_port: int = 22,
        ssh_key_path: Optional[str] = None,
        workspace_id: Optional[int] = None,
    ) -> dict:
        create_kwargs: dict = dict(
            name=name,
            path=path,
            type=type,
            ssh_host=ssh_host,
            ssh_user=ssh_user,
            ssh_port=ssh_port,
            ssh_key_path=ssh_key_path,
            owner_id=owner_id,
        )
        if workspace_id is not None:
            create_kwargs["workspace_id"] = workspace_id
        entity = ClaudeCodeProject(**create_kwargs)
        self.session.add(entity)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity.to_dict()

    async def delete_project(
        self, project_id: int, owner_id: int, workspace_id: Optional[int] = None
    ) -> bool:
        entity = await self.get_by_id_ws(project_id, workspace_id)
        if entity and entity.owner_id == owner_id:
            await self.delete(entity)
            return True
        return False
