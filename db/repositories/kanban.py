"""Repository for kanban task management."""

import json
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import KanbanChecklistItem, KanbanTask, KanbanTaskDependency
from db.repositories.base import BaseRepository


class KanbanRepository(BaseRepository[KanbanTask]):
    """Repository for kanban tasks with checklist and dependency support."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, KanbanTask)

    def _load_options(self):
        return [
            selectinload(KanbanTask.checklist),
            selectinload(KanbanTask.dependencies_as_blocker),
            selectinload(KanbanTask.dependencies_as_dependent),
        ]

    async def get_task_with_relations(
        self, task_id: int, workspace_id: Optional[int] = None
    ) -> Optional[KanbanTask]:
        """Get a single task with all relations loaded."""
        query = select(KanbanTask).where(KanbanTask.id == task_id).options(*self._load_options())
        query = self._apply_workspace_filter(query, workspace_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_visible_tasks(
        self,
        current_user_id: int,
        is_admin: bool,
        workspace_id: Optional[int] = None,
    ) -> List[dict]:
        """Get tasks visible to the user (local tasks only, project_id IS NULL).

        Admin sees all tasks.
        Others see their own tasks + non-draft public tasks.
        """
        return await self.get_visible_tasks_for_project(
            None, current_user_id, is_admin, workspace_id=workspace_id
        )

    async def get_visible_tasks_for_project(
        self,
        project_id: Optional[int],
        current_user_id: int,
        is_admin: bool,
        workspace_id: Optional[int] = None,
    ) -> List[dict]:
        """Get tasks visible to the user, filtered by project.

        project_id=None -> local tasks (project_id IS NULL)
        project_id=N -> tasks for that project
        """
        stmt = select(KanbanTask).options(*self._load_options())
        stmt = self._apply_workspace_filter(stmt, workspace_id)

        if project_id is None:
            stmt = stmt.where(KanbanTask.project_id.is_(None))
        else:
            stmt = stmt.where(KanbanTask.project_id == project_id)

        if not is_admin:
            stmt = stmt.where(
                (KanbanTask.owner_id == current_user_id)
                | ((KanbanTask.is_private == False) & (KanbanTask.status != "draft"))
            )

        stmt = stmt.order_by(KanbanTask.position, KanbanTask.id)
        result = await self.session.execute(stmt)
        tasks = result.scalars().all()
        return [t.to_dict() for t in tasks]

    async def create_task(
        self,
        title: str,
        created_by: str,
        owner_id: Optional[int] = None,
        description: Optional[str] = None,
        status: str = "todo",
        assignee: Optional[str] = None,
        start_date: Optional[str] = None,
        due_date: Optional[str] = None,
        tags: Optional[str] = None,
        workspace_id: Optional[int] = None,
    ) -> dict:
        """Create a new task (private by default)."""
        create_kwargs: dict = dict(
            title=title,
            description=description,
            status=status,
            is_private=True,
            assignee=assignee,
            created_by=created_by,
            owner_id=owner_id,
            start_date=start_date,
            due_date=due_date,
            tags=tags,
        )
        if workspace_id is not None:
            create_kwargs["workspace_id"] = workspace_id
        task = KanbanTask(**create_kwargs)
        self.session.add(task)
        await self.session.flush()
        task = await self.get_task_with_relations(task.id)
        return task.to_dict()

    async def update_task(self, task_id: int, **kwargs) -> Optional[dict]:
        """Update task fields."""
        task = await self.session.get(KanbanTask, task_id)
        if not task:
            return None

        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)

        # If moving out of draft, make public
        if "status" in kwargs and kwargs["status"] != "draft":
            task.is_private = False

        await self.session.flush()
        task = await self.get_task_with_relations(task_id)
        return task.to_dict()

    async def reorder(self, task_id: int, new_status: str, new_position: int) -> Optional[dict]:
        """Update task status and position (for drag-and-drop)."""
        task = await self.session.get(KanbanTask, task_id)
        if not task:
            return None

        task.status = new_status
        task.position = new_position
        if new_status != "draft":
            task.is_private = False

        await self.session.flush()
        task = await self.get_task_with_relations(task_id)
        return task.to_dict()

    async def _creates_cycle(self, blocker_id: int, dependent_id: int) -> bool:
        """DFS check: would adding blocker→dependent create a cycle?

        A cycle exists if dependent can reach blocker through existing
        dependency chains.
        """
        visited = set()
        stack = [blocker_id]

        while stack:
            current = stack.pop()
            if current == dependent_id:
                return True
            if current in visited:
                continue
            visited.add(current)

            # Find all tasks that current depends on (current is dependent)
            result = await self.session.execute(
                select(KanbanTaskDependency.blocker_id).where(
                    KanbanTaskDependency.dependent_id == current
                )
            )
            for row in result.all():
                stack.append(row[0])

        return False

    async def add_dependency(self, blocker_id: int, dependent_id: int) -> None:
        """Add a dependency (blocker blocks dependent).

        Raises ValueError on cycle detection.
        """
        if blocker_id == dependent_id:
            raise ValueError("A task cannot depend on itself")

        if await self._creates_cycle(dependent_id, blocker_id):
            raise ValueError("Adding this dependency would create a cycle")

        # Check if already exists
        existing = await self.session.get(KanbanTaskDependency, (blocker_id, dependent_id))
        if existing:
            return

        dep = KanbanTaskDependency(blocker_id=blocker_id, dependent_id=dependent_id)
        self.session.add(dep)
        await self.session.flush()

    async def remove_dependency(self, blocker_id: int, dependent_id: int) -> bool:
        """Remove a dependency link."""
        dep = await self.session.get(KanbanTaskDependency, (blocker_id, dependent_id))
        if not dep:
            return False
        await self.session.delete(dep)
        await self.session.flush()
        return True

    async def add_checklist_item(self, task_id: int, text: str, position: int = 0) -> dict:
        """Add a checklist item to a task."""
        item = KanbanChecklistItem(task_id=task_id, text=text, position=position)
        self.session.add(item)
        await self.session.flush()
        return item.to_dict()

    async def toggle_checklist_item(self, item_id: int) -> Optional[dict]:
        """Toggle checklist item done status."""
        item = await self.session.get(KanbanChecklistItem, item_id)
        if not item:
            return None
        item.is_done = not item.is_done
        await self.session.flush()
        return item.to_dict()

    async def delete_checklist_item(self, item_id: int) -> bool:
        """Delete a checklist item."""
        item = await self.session.get(KanbanChecklistItem, item_id)
        if not item:
            return False
        await self.session.delete(item)
        await self.session.flush()
        return True

    async def find_by_github_issue(
        self, project_id: int, issue_number: int
    ) -> Optional[KanbanTask]:
        """Find task by project and GitHub issue number."""
        result = await self.session.execute(
            select(KanbanTask)
            .options(*self._load_options())
            .where(
                KanbanTask.project_id == project_id,
                KanbanTask.github_issue_number == issue_number,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_from_github(self, project_id: int, issue_number: int, **fields) -> dict:
        """Find existing task by (project_id, issue_number), update or create."""
        task = await self.find_by_github_issue(project_id, issue_number)
        if task:
            for key, value in fields.items():
                if hasattr(task, key):
                    setattr(task, key, value)
            await self.session.flush()
            task = await self.get_task_with_relations(task.id)
            return task.to_dict()
        else:
            tags_raw = fields.pop("tags", None)
            tags_json = json.dumps(tags_raw, ensure_ascii=False) if tags_raw else None
            task = KanbanTask(
                project_id=project_id,
                github_issue_number=issue_number,
                tags=tags_json,
                **fields,
            )
            self.session.add(task)
            await self.session.flush()
            task = await self.get_task_with_relations(task.id)
            return task.to_dict()
