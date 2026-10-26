"""Google Drive sources — CRUD + sync.

A source is a Drive folder or a set of files that feeds a knowledge collection
(`rag`), the supplier price folder (`prices`), or both. Sync logic and the
daily check live in `modules/knowledge/drive_sources.py`.
"""

import asyncio
import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth_manager import User, require_permission
from db.database import AsyncSessionLocal
from modules.core.events import DatasetSynced
from modules.knowledge.drive_sources import (
    feeds_prices,
    feeds_rag,
    is_running,
    new_collection,
    sync_project,
)
from modules.knowledge.models import GoogleDriveProject, KnowledgeCollection


try:
    from sqlalchemy import delete, select
except ImportError:
    from sqlalchemy import delete
    from sqlalchemy.future import select  # type: ignore[assignment]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/google-drive", tags=["google-drive-rag"])


class CreateGoogleDriveProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    folder_id: str = Field(default="root")
    folder_name: str | None = None
    purpose: Literal["rag", "prices", "both"] = "rag"
    file_ids: list[str] = Field(default_factory=list)
    auto_sync: bool = True


class UpdateGoogleDriveProjectRequest(BaseModel):
    name: str | None = None
    auto_sync: bool | None = None
    file_ids: list[str] | None = None


async def _get_project(session, project_id: int) -> GoogleDriveProject:
    result = await session.execute(
        select(GoogleDriveProject).where(GoogleDriveProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _to_dict(project: GoogleDriveProject) -> dict:
    data = project.to_dict()
    if data["sync_status"] == "syncing" and not is_running(project.id):
        # Left over from a crash/restart mid-sync
        data["sync_status"] = "idle"
    return data


@router.get("/projects")
async def list_projects(
    _user: User = Depends(require_permission("wiki", "view")),
):
    """List all Google Drive sources."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GoogleDriveProject).order_by(GoogleDriveProject.id.desc())
        )
        projects = result.scalars().all()
        return [_to_dict(p) for p in projects]


@router.post("/projects")
async def create_project(
    req: CreateGoogleDriveProjectRequest,
    user: User = Depends(require_permission("wiki", "edit")),
):
    """Create a Google Drive source and start the initial sync."""
    if feeds_prices(req.purpose) and req.folder_id == "root" and not req.file_ids:
        raise HTTPException(
            status_code=400,
            detail="Для прайсов выберите конкретную папку или файлы, а не весь «Мой диск»",
        )

    async with AsyncSessionLocal() as session:
        collection_id = None
        if feeds_rag(req.purpose):
            collection = new_collection(req.name, req.folder_name or req.folder_id)
            session.add(collection)
            await session.flush()
            collection_id = collection.id

        project = GoogleDriveProject(
            name=req.name,
            user_id=user.id,
            folder_id=req.folder_id,
            folder_name=req.folder_name,
            collection_id=collection_id,
            purpose=req.purpose,
            file_ids=json.dumps(req.file_ids) if req.file_ids else None,
            auto_sync=req.auto_sync,
            sync_status="syncing",
            workspace_id=1,
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)
        project_dict = project.to_dict()

    # Start sync in background
    asyncio.create_task(sync_project(project_dict["id"], force=True))

    return project_dict


@router.patch("/projects/{project_id}")
async def update_project(
    project_id: int,
    req: UpdateGoogleDriveProjectRequest,
    _user: User = Depends(require_permission("wiki", "edit")),
):
    """Rename, toggle the daily check, or change the selected files."""
    async with AsyncSessionLocal() as session:
        project = await _get_project(session, project_id)
        if req.name is not None:
            project.name = req.name
        if req.auto_sync is not None:
            project.auto_sync = req.auto_sync
        if req.file_ids is not None:
            project.file_ids = json.dumps(req.file_ids) if req.file_ids else None
        await session.commit()
        await session.refresh(project)
        return _to_dict(project)


@router.post("/projects/{project_id}/sync")
async def sync_project_now(
    project_id: int,
    force: bool = True,
    _user: User = Depends(require_permission("wiki", "edit")),
):
    """Sync now. `force=false` only syncs if something changed on Drive."""
    async with AsyncSessionLocal() as session:
        await _get_project(session, project_id)
    if is_running(project_id):
        raise HTTPException(status_code=409, detail="Sync already in progress")

    asyncio.create_task(sync_project(project_id, force=force))
    return {"status": "syncing"}


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: int,
    _user: User = Depends(require_permission("wiki", "manage")),
):
    """Delete a Google Drive source and its knowledge collection.

    Price files already delivered stay in the price folder: removing them would
    leave the suppliers on their old offers with nothing to replace them.
    """
    async with AsyncSessionLocal() as session:
        project = await _get_project(session, project_id)
        collection_id = project.collection_id
        collection = None
        if collection_id:
            result = await session.execute(
                select(KnowledgeCollection).where(KnowledgeCollection.id == collection_id)
            )
            collection = result.scalar_one_or_none()

        await session.execute(delete(GoogleDriveProject).where(GoogleDriveProject.id == project_id))
        await session.commit()

    if collection:
        from app.dependencies import ServiceContainer

        container = ServiceContainer.get_instance()
        if container and container.event_bus:
            await container.event_bus.publish(
                DatasetSynced(
                    source="google_drive",
                    collection_slug=collection.slug,
                    action="cleared",
                    collection_name=collection.name,
                    collection_description="",
                    base_dir=collection.base_dir or "",
                    documents=[],
                    delete_collection=True,
                )
            )

    return {"status": "ok"}
