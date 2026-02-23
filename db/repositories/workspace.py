"""Repository for workspace operations."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Workspace, WorkspaceMember
from db.repositories.base import BaseRepository


class WorkspaceRepository(BaseRepository[Workspace]):
    """Repository for workspace CRUD and membership management."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Workspace)

    async def get_member_role_name(self, user_id: int, workspace_id: int) -> Optional[str]:
        """Get role_name for (user_id, workspace_id) from workspace_members."""
        result = await self.session.execute(
            select(WorkspaceMember.role_name).where(
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def ensure_membership(self, workspace_id: int, user_id: int, role_name: str) -> None:
        """Insert or update workspace membership (idempotent)."""
        result = await self.session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()
        if member:
            member.role_name = role_name
        else:
            self.session.add(
                WorkspaceMember(
                    workspace_id=workspace_id,
                    user_id=user_id,
                    role_name=role_name,
                )
            )
        await self.session.commit()

    async def get_default_workspace(self) -> Optional[dict]:
        """Get workspace with id=1."""
        ws = await self.get_by_id(1)
        return ws.to_dict() if ws else None

    async def create_default(self, name: str = "Default", slug: str = "default") -> dict:
        """Create the default workspace (id=1)."""
        ws = Workspace(name=name, slug=slug)
        self.session.add(ws)
        await self.session.commit()
        await self.session.refresh(ws)
        return ws.to_dict()
