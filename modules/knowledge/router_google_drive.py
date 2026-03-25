"""Google Drive RAG projects — CRUD + sync."""

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth_manager import User, require_permission
from db.database import AsyncSessionLocal
from modules.core.events import DatasetSynced
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


class UpdateGoogleDriveProjectRequest(BaseModel):
    name: str | None = None
    folder_id: str | None = None
    folder_name: str | None = None


@router.get("/projects")
async def list_projects(
    _user: User = Depends(require_permission("wiki", "view")),
):
    """List all Google Drive RAG projects."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GoogleDriveProject).order_by(GoogleDriveProject.id.desc())
        )
        projects = result.scalars().all()
        return [p.to_dict() for p in projects]


@router.post("/projects")
async def create_project(
    req: CreateGoogleDriveProjectRequest,
    user: User = Depends(require_permission("wiki", "edit")),
):
    """Create a Google Drive RAG project and start initial sync."""
    slug = f"gdrive-{req.name.lower().replace(' ', '-')[:50]}"

    async with AsyncSessionLocal() as session:
        # Create collection
        collection = KnowledgeCollection(
            name=f"Google Drive: {req.name}",
            slug=slug,
            description=f"Synced from Google Drive folder: {req.folder_name or req.folder_id}",
            base_dir=f"data/google-drive/{slug}",
            workspace_id=1,
        )
        session.add(collection)
        await session.flush()

        # Create project
        project = GoogleDriveProject(
            name=req.name,
            user_id=user.id,
            folder_id=req.folder_id,
            folder_name=req.folder_name,
            collection_id=collection.id,
            sync_status="syncing",
            workspace_id=1,
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)
        project_dict = project.to_dict()

    # Start sync in background
    asyncio.create_task(_sync_project(project_dict["id"]))

    return project_dict


@router.post("/projects/{project_id}/sync")
async def sync_project(
    project_id: int,
    _user: User = Depends(require_permission("wiki", "edit")),
):
    """Manually trigger sync for a Google Drive project."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GoogleDriveProject).where(GoogleDriveProject.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        if project.sync_status == "syncing":
            raise HTTPException(status_code=409, detail="Sync already in progress")

        project.sync_status = "syncing"
        project.sync_error = None
        await session.commit()

    asyncio.create_task(_sync_project(project_id))
    return {"status": "syncing"}


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: int,
    _user: User = Depends(require_permission("wiki", "manage")),
):
    """Delete a Google Drive RAG project."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GoogleDriveProject).where(GoogleDriveProject.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        collection_id = project.collection_id

        # Delete project
        await session.execute(delete(GoogleDriveProject).where(GoogleDriveProject.id == project_id))
        await session.commit()

    # Publish clear event if collection existed
    if collection_id:
        from app.dependencies import ServiceContainer

        container = ServiceContainer.get_instance()
        if container and container.event_bus:
            await container.event_bus.publish(
                DatasetSynced(
                    source="google_drive",
                    collection_slug="",
                    action="cleared",
                    collection_name="",
                    collection_description="",
                    base_dir="",
                    documents=[],
                    delete_collection=True,
                )
            )

    return {"status": "ok"}


async def _sync_project(project_id: int) -> None:
    """Background task: sync Google Drive folder to RAG collection."""
    from app.services.google_drive_sync_service import sync_drive_folder
    from modules.google.service import google_oauth_service

    try:
        # Load project
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(GoogleDriveProject).where(GoogleDriveProject.id == project_id)
            )
            project = result.scalar_one_or_none()
            if not project:
                return

            user_id = project.user_id
            folder_id = project.folder_id
            collection_id = project.collection_id

            # Get collection info
            col_result = await session.execute(
                select(KnowledgeCollection).where(KnowledgeCollection.id == collection_id)
            )
            collection = col_result.scalar_one_or_none()
            if not collection:
                return

            slug = collection.slug
            base_dir = collection.base_dir
            col_name = collection.name
            col_desc = collection.description or ""

        # Get valid Google credentials
        creds = await google_oauth_service.get_valid_credentials(user_id)
        if not creds:
            raise ValueError("Google not connected — re-authenticate in Settings")

        # Sync files
        from pathlib import Path as _Path

        _Path(base_dir).mkdir(parents=True, exist_ok=True)
        documents = await sync_drive_folder(creds["access_token"], folder_id, base_dir)

        # Update project status
        total_size = sum(d["file_size_bytes"] for d in documents)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(GoogleDriveProject).where(GoogleDriveProject.id == project_id)
            )
            project = result.scalar_one_or_none()
            if project:
                project.sync_status = "idle"
                project.sync_error = None
                project.last_synced = datetime.utcnow()
                project.file_count = len(documents)
                project.total_size_bytes = total_size
                await session.commit()

        # Publish DatasetSynced event
        from app.dependencies import ServiceContainer

        container = ServiceContainer.get_instance()
        if container and container.event_bus:
            await container.event_bus.publish(
                DatasetSynced(
                    source="google_drive",
                    collection_slug=slug,
                    action="synced",
                    collection_name=col_name,
                    collection_description=col_desc,
                    base_dir=base_dir,
                    documents=documents,
                    delete_collection=False,
                )
            )

        logger.info(
            f"Google Drive sync OK: project {project_id}, "
            f"{len(documents)} docs, {total_size / 1024:.1f} KB"
        )

    except Exception as e:
        logger.error(f"Google Drive sync failed for project {project_id}: {e}")
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(GoogleDriveProject).where(GoogleDriveProject.id == project_id)
            )
            project = result.scalar_one_or_none()
            if project:
                project.sync_status = "error"
                project.sync_error = str(e)[:500]
                await session.commit()
