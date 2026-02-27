"""Repository for Claude Code sessions."""

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ClaudeCodeSession
from db.repositories.base import BaseRepository


class ClaudeCodeRepository(BaseRepository[ClaudeCodeSession]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ClaudeCodeSession)

    async def list_sessions(
        self,
        owner_id: Optional[int] = None,
        limit: int = 50,
        workspace_id: Optional[int] = None,
    ) -> List[dict]:
        query = select(ClaudeCodeSession).order_by(ClaudeCodeSession.updated.desc())
        query = self._apply_workspace_filter(query, workspace_id)
        if owner_id is not None:
            query = query.where(ClaudeCodeSession.owner_id == owner_id)
        query = query.limit(limit)
        result = await self.session.execute(query)
        return [s.to_dict() for s in result.scalars().all()]

    async def get_session(
        self, session_id: str, workspace_id: Optional[int] = None
    ) -> Optional[dict]:
        entity = await self.get_by_id_ws(session_id, workspace_id)
        return entity.to_dict() if entity else None

    async def create_session(
        self,
        title: str,
        owner_id: int,
        working_directory: str = "/opt/ai-secretary",
        workspace_id: Optional[int] = None,
    ) -> dict:
        session_id = f"cc-{uuid.uuid4().hex[:12]}"
        create_kwargs: dict = dict(
            id=session_id,
            title=title[:50] if title else "New session",
            owner_id=owner_id,
            working_directory=working_directory,
        )
        if workspace_id is not None:
            create_kwargs["workspace_id"] = workspace_id
        entity = ClaudeCodeSession(**create_kwargs)
        self.session.add(entity)
        await self.session.commit()
        return entity.to_dict()

    async def update_session(self, session_id: str, **kwargs) -> Optional[dict]:
        entity = await self.get_by_id(session_id)
        if not entity:
            return None
        for key, value in kwargs.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
        entity.updated = datetime.utcnow()
        await self.session.commit()
        return entity.to_dict()

    async def delete_session(self, session_id: str, workspace_id: Optional[int] = None) -> bool:
        entity = await self.get_by_id_ws(session_id, workspace_id)
        if entity:
            await self.delete(entity)
            return True
        return False
