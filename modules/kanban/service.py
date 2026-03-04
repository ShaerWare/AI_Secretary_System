"""Kanban services."""

import logging
from typing import Optional

from db.database import AsyncSessionLocal
from db.repositories import KanbanProjectRepository, KanbanRepository


logger = logging.getLogger(__name__)


class KanbanService:
    """Async kanban task manager."""

    async def get_visible_tasks(
        self,
        current_user_id: int,
        is_admin: bool,
        workspace_id: Optional[int] = None,
    ) -> list:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            return await repo.get_visible_tasks(
                current_user_id, is_admin, workspace_id=workspace_id
            )

    async def get_task(self, task_id: int, workspace_id: Optional[int] = None) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            task = await repo.get_task_with_relations(task_id, workspace_id=workspace_id)
            return task.to_dict() if task else None

    async def create_task(self, **kwargs) -> dict:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            result = await repo.create_task(**kwargs)
            await session.commit()
            return result

    async def update_task(self, task_id: int, **kwargs) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            result = await repo.update_task(task_id, **kwargs)
            await session.commit()
            return result

    async def delete_task(self, task_id: int) -> bool:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            result = await repo.delete_by_id(task_id)
            await session.commit()
            return result

    async def reorder(self, task_id: int, new_status: str, new_position: int) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            result = await repo.reorder(task_id, new_status, new_position)
            await session.commit()
            return result

    async def add_dependency(self, blocker_id: int, dependent_id: int) -> None:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            await repo.add_dependency(blocker_id, dependent_id)
            await session.commit()

    async def remove_dependency(self, blocker_id: int, dependent_id: int) -> bool:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            result = await repo.remove_dependency(blocker_id, dependent_id)
            await session.commit()
            return result

    async def add_checklist_item(self, task_id: int, text: str, position: int = 0) -> dict:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            result = await repo.add_checklist_item(task_id, text, position)
            await session.commit()
            return result

    async def toggle_checklist_item(self, item_id: int) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            result = await repo.toggle_checklist_item(item_id)
            await session.commit()
            return result

    async def delete_checklist_item(self, item_id: int) -> bool:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            result = await repo.delete_checklist_item(item_id)
            await session.commit()
            return result

    async def get_visible_tasks_for_project(
        self,
        project_id,
        current_user_id: int,
        is_admin: bool,
        workspace_id: Optional[int] = None,
    ) -> list:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            return await repo.get_visible_tasks_for_project(
                project_id, current_user_id, is_admin, workspace_id=workspace_id
            )

    async def find_by_github_issue(self, project_id: int, issue_number: int):
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            task = await repo.find_by_github_issue(project_id, issue_number)
            return task.to_dict() if task else None

    async def upsert_from_github(self, project_id: int, issue_number: int, **fields) -> dict:
        async with AsyncSessionLocal() as session:
            repo = KanbanRepository(session)
            result = await repo.upsert_from_github(project_id, issue_number, **fields)
            await session.commit()
            return result


class KanbanProjectService:
    """Async kanban project manager."""

    async def get_all_projects(self, workspace_id: Optional[int] = None) -> list:
        async with AsyncSessionLocal() as session:
            repo = KanbanProjectRepository(session)
            return await repo.get_all_projects(workspace_id=workspace_id)

    async def get_project(
        self, project_id: int, workspace_id: Optional[int] = None
    ) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = KanbanProjectRepository(session)
            project = await repo.get_project_with_token(project_id, workspace_id=workspace_id)
            return project.to_dict() if project else None

    async def get_project_with_token(self, project_id: int):
        """Returns ORM object with raw token for sync operations."""
        async with AsyncSessionLocal() as session:
            repo = KanbanProjectRepository(session)
            project = await repo.get_project_with_token(project_id)
            if not project:
                return None
            # Return a plain dict with token included (for internal use only)
            d = project.to_dict()
            d["github_token"] = project.github_token
            d["webhook_secret"] = project.webhook_secret
            d["_label_mapping"] = project.get_label_mapping()
            d["_reverse_label_mapping"] = project.get_reverse_label_mapping()
            return d

    async def get_by_repo(self, owner: str, repo: str):
        """Find project by GitHub owner/repo. Returns dict with token."""
        async with AsyncSessionLocal() as session:
            repo_obj = KanbanProjectRepository(session)
            project = await repo_obj.get_by_repo(owner, repo)
            if not project:
                return None
            d = project.to_dict()
            d["github_token"] = project.github_token
            d["webhook_secret"] = project.webhook_secret
            d["_label_mapping"] = project.get_label_mapping()
            d["_reverse_label_mapping"] = project.get_reverse_label_mapping()
            return d

    async def create_project(self, **kwargs) -> dict:
        async with AsyncSessionLocal() as session:
            repo = KanbanProjectRepository(session)
            result = await repo.create_project(**kwargs)
            await session.commit()
            return result

    async def update_project(self, project_id: int, **kwargs) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            repo = KanbanProjectRepository(session)
            result = await repo.update_project(project_id, **kwargs)
            await session.commit()
            return result

    async def delete_project(self, project_id: int) -> bool:
        async with AsyncSessionLocal() as session:
            repo = KanbanProjectRepository(session)
            result = await repo.delete_by_id(project_id)
            await session.commit()
            return result

    async def update_last_synced(self, project_id: int) -> None:
        async with AsyncSessionLocal() as session:
            repo = KanbanProjectRepository(session)
            await repo.update_last_synced(project_id)
            await session.commit()


# Singletons
kanban_service = KanbanService()
kanban_project_service = KanbanProjectService()
