"""Kanban task management API endpoints."""

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth_manager import User, get_current_user, require_admin, require_not_guest
from db.integration import async_audit_logger, async_kanban_manager


router = APIRouter(prefix="/admin/kanban", tags=["kanban"])


# ============== Pydantic Schemas ==============


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    assignee: Optional[str] = None
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    tags: Optional[List[str]] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    status: Optional[str] = None
    assignee: Optional[str] = None
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    tags: Optional[List[str]] = None
    is_private: Optional[bool] = None


class TaskReorder(BaseModel):
    task_id: int
    new_status: str
    new_position: int


class DependencyCreate(BaseModel):
    blocker_id: int
    dependent_id: int


class ChecklistItemCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    position: int = 0


# ============== Task Endpoints ==============


@router.get("/tasks")
async def get_tasks(user: User = Depends(get_current_user)):
    """Get all tasks visible to the current user."""
    is_admin = user.role == "admin"
    tasks = await async_kanban_manager.get_visible_tasks(user.username, is_admin)
    return {"tasks": tasks}


@router.post("/tasks")
async def create_task(request: TaskCreate, user: User = Depends(require_not_guest)):
    """Create a new task (always draft + private)."""
    tags_json = json.dumps(request.tags, ensure_ascii=False) if request.tags else None
    task = await async_kanban_manager.create_task(
        title=request.title,
        description=request.description,
        assignee=request.assignee,
        start_date=request.start_date,
        due_date=request.due_date,
        tags=tags_json,
        created_by=user.username,
    )
    await async_audit_logger.log(
        action="create",
        resource="kanban_task",
        resource_id=str(task["id"]),
        user_id=user.username,
    )
    return {"task": task}


@router.patch("/tasks/{task_id}")
async def update_task(task_id: int, request: TaskUpdate, user: User = Depends(require_not_guest)):
    """Update a task. Non-admin can only edit own tasks."""
    existing = await async_kanban_manager.get_task(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    if user.role != "admin" and existing["created_by"] != user.username:
        raise HTTPException(status_code=403, detail="Can only edit own tasks")

    update_data = {}
    if request.title is not None:
        update_data["title"] = request.title
    if request.description is not None:
        update_data["description"] = request.description
    if request.status is not None:
        update_data["status"] = request.status
    if request.assignee is not None:
        update_data["assignee"] = request.assignee
    if request.start_date is not None:
        update_data["start_date"] = request.start_date
    if request.due_date is not None:
        update_data["due_date"] = request.due_date
    if request.tags is not None:
        update_data["tags"] = json.dumps(request.tags, ensure_ascii=False)
    if request.is_private is not None:
        update_data["is_private"] = request.is_private

    task = await async_kanban_manager.update_task(task_id, **update_data)
    await async_audit_logger.log(
        action="update",
        resource="kanban_task",
        resource_id=str(task_id),
        user_id=user.username,
    )
    return {"task": task}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int, user: User = Depends(require_admin)):
    """Delete a task (admin only)."""
    existing = await async_kanban_manager.get_task(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    await async_kanban_manager.delete_task(task_id)
    await async_audit_logger.log(
        action="delete",
        resource="kanban_task",
        resource_id=str(task_id),
        user_id=user.username,
    )
    return {"status": "ok"}


# ============== Reorder ==============


@router.post("/reorder")
async def reorder_task(request: TaskReorder, user: User = Depends(require_not_guest)):
    """Reorder a task (update status + position)."""
    task = await async_kanban_manager.reorder(
        request.task_id, request.new_status, request.new_position
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": task}


# ============== Dependencies ==============


@router.post("/dependencies")
async def add_dependency(request: DependencyCreate, user: User = Depends(require_not_guest)):
    """Add a dependency between tasks."""
    # Check target task exists and is not private
    target = await async_kanban_manager.get_task(request.blocker_id)
    if not target:
        raise HTTPException(status_code=404, detail="Blocker task not found")
    if target["is_private"] and target["created_by"] != user.username and user.role != "admin":
        raise HTTPException(status_code=409, detail="Cannot depend on a private task")

    dependent = await async_kanban_manager.get_task(request.dependent_id)
    if not dependent:
        raise HTTPException(status_code=404, detail="Dependent task not found")

    try:
        await async_kanban_manager.add_dependency(request.blocker_id, request.dependent_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"status": "ok"}


@router.delete("/dependencies")
async def remove_dependency(
    blocker_id: int = Query(...),
    dependent_id: int = Query(...),
    user: User = Depends(require_not_guest),
):
    """Remove a dependency between tasks."""
    removed = await async_kanban_manager.remove_dependency(blocker_id, dependent_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Dependency not found")
    return {"status": "ok"}


# ============== Checklist ==============


@router.post("/tasks/{task_id}/checklist")
async def add_checklist_item(
    task_id: int,
    request: ChecklistItemCreate,
    user: User = Depends(require_not_guest),
):
    """Add a checklist item to a task."""
    existing = await async_kanban_manager.get_task(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    item = await async_kanban_manager.add_checklist_item(task_id, request.text, request.position)
    return {"item": item}


@router.patch("/checklist/{item_id}/toggle")
async def toggle_checklist_item(item_id: int, user: User = Depends(require_not_guest)):
    """Toggle a checklist item's done status."""
    item = await async_kanban_manager.toggle_checklist_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    return {"item": item}


@router.delete("/checklist/{item_id}")
async def delete_checklist_item(item_id: int, user: User = Depends(require_not_guest)):
    """Delete a checklist item."""
    deleted = await async_kanban_manager.delete_checklist_item(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    return {"status": "ok"}
