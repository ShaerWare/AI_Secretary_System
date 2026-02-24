"""Kanban task management API endpoints."""

import json
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth_manager import User, require_permission, user_has_level, workspace_context
from db.integration import async_audit_logger, async_kanban_manager, async_kanban_project_manager


logger = logging.getLogger(__name__)

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


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    github_owner: str = Field(..., min_length=1, max_length=100)
    github_repo: str = Field(..., min_length=1, max_length=100)
    github_token: Optional[str] = None
    webhook_secret: Optional[str] = None
    label_mapping: Optional[Dict[str, str]] = None
    sync_enabled: bool = True


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    github_owner: Optional[str] = Field(None, min_length=1, max_length=100)
    github_repo: Optional[str] = Field(None, min_length=1, max_length=100)
    github_token: Optional[str] = None
    webhook_secret: Optional[str] = None
    label_mapping: Optional[Dict[str, str]] = None
    sync_enabled: Optional[bool] = None


# ============== Project Endpoints ==============


@router.get("/projects")
async def get_projects(user: User = Depends(require_permission("kanban", "view"))):
    """Get all kanban projects."""
    _owner_id, ws_id = workspace_context(user, "kanban")
    projects = await async_kanban_project_manager.get_all_projects(workspace_id=ws_id)
    return {"projects": projects}


@router.post("/projects")
async def create_project(
    request: ProjectCreate, user: User = Depends(require_permission("kanban", "manage"))
):
    """Create a new kanban project (admin only)."""
    _owner_id, ws_id = workspace_context(user, "kanban")
    kwargs = {
        "name": request.name,
        "github_owner": request.github_owner,
        "github_repo": request.github_repo,
        "sync_enabled": request.sync_enabled,
        "workspace_id": ws_id,
    }
    if request.github_token:
        kwargs["github_token"] = request.github_token
    if request.webhook_secret:
        kwargs["webhook_secret"] = request.webhook_secret
    if request.label_mapping:
        kwargs["label_mapping"] = json.dumps(request.label_mapping, ensure_ascii=False)

    project = await async_kanban_project_manager.create_project(**kwargs)
    await async_audit_logger.log(
        action="create",
        resource="kanban_project",
        resource_id=str(project["id"]),
        user_id=user.username,
    )
    return {"project": project}


@router.patch("/projects/{project_id}")
async def update_project(
    project_id: int,
    request: ProjectUpdate,
    user: User = Depends(require_permission("kanban", "manage")),
):
    """Update a kanban project (admin only)."""
    _owner_id, ws_id = workspace_context(user, "kanban")
    existing = await async_kanban_project_manager.get_project(project_id, workspace_id=ws_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    update_data = {}
    if request.name is not None:
        update_data["name"] = request.name
    if request.github_owner is not None:
        update_data["github_owner"] = request.github_owner
    if request.github_repo is not None:
        update_data["github_repo"] = request.github_repo
    if request.github_token is not None:
        update_data["github_token"] = request.github_token
    if request.webhook_secret is not None:
        update_data["webhook_secret"] = request.webhook_secret
    if request.label_mapping is not None:
        update_data["label_mapping"] = json.dumps(request.label_mapping, ensure_ascii=False)
    if request.sync_enabled is not None:
        update_data["sync_enabled"] = request.sync_enabled

    project = await async_kanban_project_manager.update_project(project_id, **update_data)
    await async_audit_logger.log(
        action="update",
        resource="kanban_project",
        resource_id=str(project_id),
        user_id=user.username,
    )
    return {"project": project}


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: int, user: User = Depends(require_permission("kanban", "manage"))
):
    """Delete a kanban project (admin only)."""
    _owner_id, ws_id = workspace_context(user, "kanban")
    existing = await async_kanban_project_manager.get_project(project_id, workspace_id=ws_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    await async_kanban_project_manager.delete_project(project_id)
    await async_audit_logger.log(
        action="delete",
        resource="kanban_project",
        resource_id=str(project_id),
        user_id=user.username,
    )
    return {"status": "deleted"}


@router.post("/projects/{project_id}/sync")
async def sync_project(project_id: int, user: User = Depends(require_permission("kanban", "edit"))):
    """Trigger full sync of GitHub issues for a project."""
    _owner_id, ws_id = workspace_context(user, "kanban")
    existing = await async_kanban_project_manager.get_project(project_id, workspace_id=ws_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.services.github_kanban_sync import sync_all_issues

    try:
        result = await sync_all_issues(project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Sync failed for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Sync failed")

    return result


# ============== Task Endpoints ==============


async def _push_github_status(task: dict, new_status: str):
    """Background task: push status change to GitHub if task is linked."""
    project_id = task.get("project_id")
    issue_number = task.get("github_issue_number")
    if not project_id or not issue_number:
        return
    try:
        from app.services.github_kanban_sync import push_status_to_github

        await push_status_to_github(project_id, issue_number, new_status)
    except Exception as e:
        logger.error(f"Failed to push status to GitHub: {e}")


@router.get("/tasks")
async def get_tasks(
    user: User = Depends(require_permission("kanban", "view")),
    project_id: Optional[int] = Query(None),
):
    """Get tasks visible to the current user, optionally filtered by project."""
    _owner_id, ws_id = workspace_context(user, "kanban")
    is_admin = user_has_level(user, "kanban", "manage")
    tasks = await async_kanban_manager.get_visible_tasks_for_project(
        project_id, user.username, is_admin, workspace_id=ws_id
    )
    return {"tasks": tasks}


@router.post("/tasks")
async def create_task(
    request: TaskCreate, user: User = Depends(require_permission("kanban", "edit"))
):
    """Create a new task (always draft + private)."""
    _owner_id, ws_id = workspace_context(user, "kanban")
    tags_json = json.dumps(request.tags, ensure_ascii=False) if request.tags else None
    task = await async_kanban_manager.create_task(
        title=request.title,
        description=request.description,
        assignee=request.assignee,
        start_date=request.start_date,
        due_date=request.due_date,
        tags=tags_json,
        created_by=user.username,
        workspace_id=ws_id,
    )
    await async_audit_logger.log(
        action="create",
        resource="kanban_task",
        resource_id=str(task["id"]),
        user_id=user.username,
    )
    return {"task": task}


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: int,
    request: TaskUpdate,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_permission("kanban", "edit")),
):
    """Update a task. Non-admin can only edit own tasks."""
    _owner_id, ws_id = workspace_context(user, "kanban")
    existing = await async_kanban_manager.get_task(task_id, workspace_id=ws_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    if not user_has_level(user, "kanban", "manage") and existing["created_by"] != user.username:
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

    # Push status change to GitHub in background
    if (
        request.status is not None
        and existing.get("project_id")
        and existing.get("github_issue_number")
    ):
        background_tasks.add_task(_push_github_status, existing, request.status)

    return {"task": task}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int, user: User = Depends(require_permission("kanban", "manage"))):
    """Delete a task (admin only)."""
    _owner_id, ws_id = workspace_context(user, "kanban")
    existing = await async_kanban_manager.get_task(task_id, workspace_id=ws_id)
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
async def reorder_task(
    request: TaskReorder,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_permission("kanban", "edit")),
):
    """Reorder a task (update status + position)."""
    _owner_id, ws_id = workspace_context(user, "kanban")
    # Get existing task before reorder (for GitHub push check)
    existing = await async_kanban_manager.get_task(request.task_id, workspace_id=ws_id)

    task = await async_kanban_manager.reorder(
        request.task_id, request.new_status, request.new_position
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Push status change to GitHub in background
    if existing and existing.get("project_id") and existing.get("github_issue_number"):
        if existing.get("status") != request.new_status:
            background_tasks.add_task(_push_github_status, existing, request.new_status)

    return {"task": task}


# ============== Dependencies ==============


@router.post("/dependencies")
async def add_dependency(
    request: DependencyCreate, user: User = Depends(require_permission("kanban", "edit"))
):
    """Add a dependency between tasks."""
    _owner_id, ws_id = workspace_context(user, "kanban")
    # Check target task exists and is not private
    target = await async_kanban_manager.get_task(request.blocker_id, workspace_id=ws_id)
    if not target:
        raise HTTPException(status_code=404, detail="Blocker task not found")
    if (
        target["is_private"]
        and target["created_by"] != user.username
        and not user_has_level(user, "kanban", "manage")
    ):
        raise HTTPException(status_code=409, detail="Cannot depend on a private task")

    dependent = await async_kanban_manager.get_task(request.dependent_id, workspace_id=ws_id)
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
    user: User = Depends(require_permission("kanban", "edit")),
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
    user: User = Depends(require_permission("kanban", "edit")),
):
    """Add a checklist item to a task."""
    _owner_id, ws_id = workspace_context(user, "kanban")
    existing = await async_kanban_manager.get_task(task_id, workspace_id=ws_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    item = await async_kanban_manager.add_checklist_item(task_id, request.text, request.position)
    return {"item": item}


@router.patch("/checklist/{item_id}/toggle")
async def toggle_checklist_item(
    item_id: int, user: User = Depends(require_permission("kanban", "edit"))
):
    """Toggle a checklist item's done status."""
    item = await async_kanban_manager.toggle_checklist_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    return {"item": item}


@router.delete("/checklist/{item_id}")
async def delete_checklist_item(
    item_id: int, user: User = Depends(require_permission("kanban", "edit"))
):
    """Delete a checklist item."""
    deleted = await async_kanban_manager.delete_checklist_item(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    return {"status": "ok"}
