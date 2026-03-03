"""Claude Code services."""

import logging
from typing import List, Optional

from db.database import AsyncSessionLocal
from db.repositories import ClaudeCodeProjectRepository, ClaudeCodeRepository


logger = logging.getLogger(__name__)


class ClaudeCodeService:
    """Manager for Claude Code session CRUD."""

    async def list_sessions(
        self,
        owner_id: Optional[int] = None,
        limit: int = 50,
        workspace_id: Optional[int] = None,
    ) -> List[dict]:
        async with AsyncSessionLocal() as session:
            repo = ClaudeCodeRepository(session)
            return await repo.list_sessions(
                owner_id=owner_id, limit=limit, workspace_id=workspace_id
            )

    async def get_session(
        self, session_id: str, workspace_id: Optional[int] = None
    ) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = ClaudeCodeRepository(session)
            return await repo.get_session(session_id, workspace_id=workspace_id)

    async def create_session(
        self,
        title: str,
        owner_id: int,
        working_directory: str = "/opt/ai-secretary",
        workspace_id: Optional[int] = None,
        chat_session_id: Optional[str] = None,
        kanban_task_id: Optional[int] = None,
    ) -> dict:
        async with AsyncSessionLocal() as session:
            repo = ClaudeCodeRepository(session)
            result = await repo.create_session(
                title,
                owner_id,
                working_directory,
                workspace_id=workspace_id,
                chat_session_id=chat_session_id,
                kanban_task_id=kanban_task_id,
            )
            await session.commit()
            return result

    async def update_session(self, session_id: str, **kwargs) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = ClaudeCodeRepository(session)
            result = await repo.update_session(session_id, **kwargs)
            await session.commit()
            return result

    async def delete_session(self, session_id: str, workspace_id: Optional[int] = None) -> bool:
        async with AsyncSessionLocal() as session:
            repo = ClaudeCodeRepository(session)
            result = await repo.delete_session(session_id, workspace_id=workspace_id)
            await session.commit()
            return result

    async def save_transcript(self, session_id: str, transcript_json: str) -> bool:
        async with AsyncSessionLocal() as session:
            repo = ClaudeCodeRepository(session)
            result = await repo.save_transcript(session_id, transcript_json)
            await session.commit()
            return result

    async def get_session_with_transcript(
        self, session_id: str, workspace_id: Optional[int] = None
    ) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = ClaudeCodeRepository(session)
            return await repo.get_session_with_transcript(session_id, workspace_id=workspace_id)

    async def list_by_chat_session(
        self, chat_session_id: str, workspace_id: Optional[int] = None
    ) -> List[dict]:
        async with AsyncSessionLocal() as session:
            repo = ClaudeCodeRepository(session)
            return await repo.list_by_chat_session(chat_session_id, workspace_id=workspace_id)

    async def list_by_kanban_task(
        self, kanban_task_id: int, workspace_id: Optional[int] = None
    ) -> List[dict]:
        async with AsyncSessionLocal() as session:
            repo = ClaudeCodeRepository(session)
            return await repo.list_by_kanban_task(kanban_task_id, workspace_id=workspace_id)


class ClaudeCodeProjectService:
    """Manager for Claude Code project CRUD."""

    async def list_projects(self, owner_id: int, workspace_id: Optional[int] = None) -> List[dict]:
        async with AsyncSessionLocal() as session:
            repo = ClaudeCodeProjectRepository(session)
            return await repo.list_projects(owner_id=owner_id, workspace_id=workspace_id)

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
        async with AsyncSessionLocal() as session:
            repo = ClaudeCodeProjectRepository(session)
            result = await repo.create_project(
                name=name,
                path=path,
                owner_id=owner_id,
                type=type,
                ssh_host=ssh_host,
                ssh_user=ssh_user,
                ssh_port=ssh_port,
                ssh_key_path=ssh_key_path,
                workspace_id=workspace_id,
            )
            await session.commit()
            return result

    async def delete_project(
        self, project_id: int, owner_id: int, workspace_id: Optional[int] = None
    ) -> bool:
        async with AsyncSessionLocal() as session:
            repo = ClaudeCodeProjectRepository(session)
            result = await repo.delete_project(project_id, owner_id, workspace_id=workspace_id)
            await session.commit()
            return result
