"""Kanban task management API endpoints."""

import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth_manager import User, require_permission, user_has_level, workspace_context
from modules.claude_code.service import claude_code_service
from modules.kanban.service import kanban_project_service, kanban_service
from modules.knowledge.service import knowledge_collection_service, knowledge_doc_service
from modules.monitoring.service import audit_service


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/kanban", tags=["kanban"])


# ============== Pydantic Schemas ==============


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    status: Optional[str] = "todo"
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
    projects = await kanban_project_service.get_all_projects(workspace_id=ws_id)
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

    project = await kanban_project_service.create_project(**kwargs)
    await audit_service.log(
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
    existing = await kanban_project_service.get_project(project_id, workspace_id=ws_id)
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

    project = await kanban_project_service.update_project(project_id, **update_data)
    await audit_service.log(
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
    existing = await kanban_project_service.get_project(project_id, workspace_id=ws_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    await kanban_project_service.delete_project(project_id)
    await audit_service.log(
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
    existing = await kanban_project_service.get_project(project_id, workspace_id=ws_id)
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
    tasks = await kanban_service.get_visible_tasks_for_project(
        project_id, user.id, is_admin, workspace_id=ws_id
    )
    return {"tasks": tasks}


@router.post("/tasks")
async def create_task(
    request: TaskCreate, user: User = Depends(require_permission("kanban", "edit"))
):
    """Create a new task (private by default)."""
    _owner_id, ws_id = workspace_context(user, "kanban")
    valid_statuses = {"draft", "todo", "in_progress", "review", "done"}
    status = request.status if request.status in valid_statuses else "todo"
    tags_json = json.dumps(request.tags, ensure_ascii=False) if request.tags else None
    task = await kanban_service.create_task(
        title=request.title,
        description=request.description,
        status=status,
        assignee=request.assignee,
        start_date=request.start_date,
        due_date=request.due_date,
        tags=tags_json,
        created_by=user.username,
        owner_id=user.id,
        workspace_id=ws_id,
    )
    await audit_service.log(
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
    existing = await kanban_service.get_task(task_id, workspace_id=ws_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    if not user_has_level(user, "kanban", "manage") and existing.get("owner_id") != user.id:
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

    task = await kanban_service.update_task(task_id, **update_data)
    await audit_service.log(
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
    existing = await kanban_service.get_task(task_id, workspace_id=ws_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    await kanban_service.delete_task(task_id)
    await audit_service.log(
        action="delete",
        resource="kanban_task",
        resource_id=str(task_id),
        user_id=user.username,
    )
    return {"status": "ok"}


@router.get("/tasks/{task_id}/cc-sessions")
async def list_cc_sessions_for_task(
    task_id: int, user: User = Depends(require_permission("kanban", "view"))
):
    """List Claude Code sessions linked to a kanban task."""
    _owner_id, ws_id = workspace_context(user, "kanban")
    sessions = await claude_code_service.list_by_kanban_task(task_id, workspace_id=ws_id)
    return {"sessions": sessions}


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
    existing = await kanban_service.get_task(request.task_id, workspace_id=ws_id)

    task = await kanban_service.reorder(request.task_id, request.new_status, request.new_position)
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
    target = await kanban_service.get_task(request.blocker_id, workspace_id=ws_id)
    if not target:
        raise HTTPException(status_code=404, detail="Blocker task not found")
    if (
        target["is_private"]
        and target.get("owner_id") != user.id
        and not user_has_level(user, "kanban", "manage")
    ):
        raise HTTPException(status_code=409, detail="Cannot depend on a private task")

    dependent = await kanban_service.get_task(request.dependent_id, workspace_id=ws_id)
    if not dependent:
        raise HTTPException(status_code=404, detail="Dependent task not found")

    try:
        await kanban_service.add_dependency(request.blocker_id, request.dependent_id)
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
    removed = await kanban_service.remove_dependency(blocker_id, dependent_id)
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
    existing = await kanban_service.get_task(task_id, workspace_id=ws_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    item = await kanban_service.add_checklist_item(task_id, request.text, request.position)
    return {"item": item}


@router.patch("/checklist/{item_id}/toggle")
async def toggle_checklist_item(
    item_id: int, user: User = Depends(require_permission("kanban", "edit"))
):
    """Toggle a checklist item's done status."""
    item = await kanban_service.toggle_checklist_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    return {"item": item}


@router.delete("/checklist/{item_id}")
async def delete_checklist_item(
    item_id: int, user: User = Depends(require_permission("kanban", "edit"))
):
    """Delete a checklist item."""
    deleted = await kanban_service.delete_checklist_item(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    return {"status": "ok"}


# ============== Dataset (RAG Knowledge Base) ==============


@router.post("/projects/{project_id}/dataset-sync")
async def dataset_sync(
    project_id: int,
    user: User = Depends(require_permission("kanban", "edit")),
):
    """Sync kanban project tasks to a RAG knowledge base collection."""
    from app.services.kanban_dataset_service import (
        build_project_summary,
        build_status_document,
        get_project_dir,
    )

    _owner_id, ws_id = workspace_context(user, "kanban")
    project = await kanban_project_service.get_project(project_id, workspace_id=ws_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_dict = {
        "id": project.id,
        "name": project.name,
        "github_owner": project.github_owner,
        "github_repo": project.github_repo,
    }

    # Fetch all tasks for this project
    is_admin = user_has_level(user, "kanban", "manage")
    tasks = await kanban_service.get_visible_tasks_for_project(
        project_id, user.id, is_admin, workspace_id=ws_id
    )

    sync_time = datetime.utcnow().strftime("%d.%m.%Y %H:%M")
    slug = f"kanban-{project.github_owner}-{project.github_repo}".lower()
    project_dir = get_project_dir(slug)
    project_dir.mkdir(parents=True, exist_ok=True)

    # Group tasks by status
    tasks_by_status: Dict[str, list] = {}
    for task in tasks:
        s = task.get("status", "todo")
        tasks_by_status.setdefault(s, []).append(task)

    # Build markdown documents
    documents: list[tuple[str, str, str]] = []  # (filename, title, content)

    for status, status_tasks in tasks_by_status.items():
        content = build_status_document(project.name, status, status_tasks, sync_time)
        filename = f"kanban-{slug}-{status}.md"
        (project_dir / filename).write_text(content, encoding="utf-8")
        documents.append((filename, f"{project.name}: {status}", content))

    # Summary document
    summary = build_project_summary(project.name, project_dict, tasks, sync_time)
    summary_filename = f"kanban-{slug}-summary.md"
    (project_dir / summary_filename).write_text(summary, encoding="utf-8")
    documents.append((summary_filename, f"{project.name}: Сводка", summary))

    # Auto-create or find collection
    collection = None
    existing_collections = await knowledge_collection_service.get_all()
    for col in existing_collections:
        if col.get("slug") == slug:
            collection = col
            break

    if not collection:
        collection = await knowledge_collection_service.create(
            name=f"Kanban: {project.name}",
            slug=slug,
            description=f"Задачи: {project.github_owner}/{project.github_repo}",
            enabled=True,
            base_dir=str(project_dir),
        )

    collection_id = collection["id"]

    # Clear existing documents for this collection
    existing_docs = await knowledge_doc_service.get_by_collection(collection_id)
    for doc in existing_docs:
        await knowledge_doc_service.delete(doc["id"])

    # Create new knowledge document records
    total_sections = 0
    for filename, title, content in documents:
        sections = len(re.findall(r"^#{2,3}\s+.+$", content, re.MULTILINE))
        total_sections += sections
        await knowledge_doc_service.create(
            filename=filename,
            title=title,
            source_type="kanban",
            file_size_bytes=len(content.encode("utf-8")),
            section_count=sections,
            collection_id=collection_id,
        )

    # Reload RAG index
    from app.dependencies import get_container

    container = get_container()
    wiki_rag = container.wiki_rag_service
    if wiki_rag:
        filenames = [d[0] for d in documents]
        wiki_rag.reload_collection(collection_id, filenames, project_dir)

    await audit_service.log(
        action="dataset_sync",
        resource="kanban_project",
        resource_id=str(project_id),
        user_id=user.username,
        details={"tasks": len(tasks), "documents": len(documents)},
    )

    return {
        "status": "ok",
        "tasks": len(tasks),
        "documents": len(documents),
        "sections": total_sections,
        "collection_id": collection_id,
        "synced_at": sync_time,
    }


@router.get("/projects/{project_id}/dataset-status")
async def dataset_status(
    project_id: int,
    user: User = Depends(require_permission("kanban", "view")),
):
    """Get dataset status for a kanban project."""
    _owner_id, ws_id = workspace_context(user, "kanban")
    project = await kanban_project_service.get_project(project_id, workspace_id=ws_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    slug = f"kanban-{project.github_owner}-{project.github_repo}".lower()

    # Find collection
    existing_collections = await knowledge_collection_service.get_all()
    collection = None
    for col in existing_collections:
        if col.get("slug") == slug:
            collection = col
            break

    if not collection:
        return {
            "synced": False,
            "collection_id": None,
            "documents": 0,
            "sections": 0,
        }

    collection_id = collection["id"]
    docs = await knowledge_doc_service.get_by_collection(collection_id)
    total_sections = sum(d.get("section_count", 0) for d in docs)

    return {
        "synced": True,
        "collection_id": collection_id,
        "documents": len(docs),
        "sections": total_sections,
    }


@router.delete("/projects/{project_id}/dataset")
async def dataset_clear(
    project_id: int,
    user: User = Depends(require_permission("kanban", "manage")),
):
    """Clear kanban dataset — remove files, DB records, and unload RAG collection."""
    from app.services.kanban_dataset_service import clean_kanban_files, get_project_dir

    _owner_id, ws_id = workspace_context(user, "kanban")
    project = await kanban_project_service.get_project(project_id, workspace_id=ws_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    slug = f"kanban-{project.github_owner}-{project.github_repo}".lower()

    # Find and delete collection
    existing_collections = await knowledge_collection_service.get_all()
    collection = None
    for col in existing_collections:
        if col.get("slug") == slug:
            collection = col
            break

    if collection:
        collection_id = collection["id"]

        # Delete knowledge documents
        docs = await knowledge_doc_service.get_by_collection(collection_id)
        for doc in docs:
            await knowledge_doc_service.delete(doc["id"])

        # Clear RAG index
        from app.dependencies import get_container

        container = get_container()
        wiki_rag = container.wiki_rag_service
        if wiki_rag:
            project_dir = get_project_dir(slug)
            wiki_rag.reload_collection(collection_id, [], project_dir)

        await knowledge_collection_service.delete(collection_id)

    # Remove files
    clean_kanban_files(slug)

    await audit_service.log(
        action="dataset_clear",
        resource="kanban_project",
        resource_id=str(project_id),
        user_id=user.username,
    )

    return {"status": "ok"}
