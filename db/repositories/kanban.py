"""Repository for kanban task management."""

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

    async def get_task_with_relations(self, task_id: int) -> Optional[KanbanTask]:
        """Get a single task with all relations loaded."""
        result = await self.session.execute(
            select(KanbanTask).where(KanbanTask.id == task_id).options(*self._load_options())
        )
        return result.scalar_one_or_none()

    async def get_visible_tasks(self, current_user: str, is_admin: bool) -> List[dict]:
        """Get tasks visible to the user.

        Admin sees all tasks.
        Others see their own tasks + non-draft public tasks.
        """
        stmt = select(KanbanTask).options(*self._load_options())

        if not is_admin:
            stmt = stmt.where(
                (KanbanTask.created_by == current_user)
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
        description: Optional[str] = None,
        assignee: Optional[str] = None,
        start_date: Optional[str] = None,
        due_date: Optional[str] = None,
        tags: Optional[str] = None,
    ) -> dict:
        """Create a new task (always draft + private)."""
        task = KanbanTask(
            title=title,
            description=description,
            status="draft",
            is_private=True,
            assignee=assignee,
            created_by=created_by,
            start_date=start_date,
            due_date=due_date,
            tags=tags,
        )
        self.session.add(task)
        await self.session.commit()
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

        await self.session.commit()
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

        await self.session.commit()
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
        await self.session.commit()

    async def remove_dependency(self, blocker_id: int, dependent_id: int) -> bool:
        """Remove a dependency link."""
        dep = await self.session.get(KanbanTaskDependency, (blocker_id, dependent_id))
        if not dep:
            return False
        await self.session.delete(dep)
        await self.session.commit()
        return True

    async def add_checklist_item(self, task_id: int, text: str, position: int = 0) -> dict:
        """Add a checklist item to a task."""
        item = KanbanChecklistItem(task_id=task_id, text=text, position=position)
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return item.to_dict()

    async def toggle_checklist_item(self, item_id: int) -> Optional[dict]:
        """Toggle checklist item done status."""
        item = await self.session.get(KanbanChecklistItem, item_id)
        if not item:
            return None
        item.is_done = not item.is_done
        await self.session.commit()
        await self.session.refresh(item)
        return item.to_dict()

    async def delete_checklist_item(self, item_id: int) -> bool:
        """Delete a checklist item."""
        item = await self.session.get(KanbanChecklistItem, item_id)
        if not item:
            return False
        await self.session.delete(item)
        await self.session.commit()
        return True
