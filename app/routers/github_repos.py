"""GitHub repository projects router — connect repos as knowledge base collections."""

import json
import logging
import re
import subprocess
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.github_repo_sync_service import (
    build_repo_documents,
    build_repo_summary,
    clean_repo_files,
    clone_repo,
    get_rag_dir,
    pull_repo,
    write_rag_documents,
)
from auth_manager import User, require_permission, workspace_context
from db.integration import (
    async_audit_logger,
    async_github_repo_project_manager,
    async_knowledge_collection_manager,
    async_knowledge_doc_manager,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/github-repos", tags=["github-repos"])


# ============== Pydantic Models ==============


class GitHubProjectCreate(BaseModel):
    name: str
    github_owner: str
    github_repo: str
    github_token: Optional[str] = None
    branch: str = "main"
    include_patterns: Optional[list[str]] = None
    exclude_patterns: Optional[list[str]] = None


class GitHubProjectUpdate(BaseModel):
    name: Optional[str] = None
    github_token: Optional[str] = None
    branch: Optional[str] = None
    include_patterns: Optional[list[str]] = None
    exclude_patterns: Optional[list[str]] = None


# ============== Endpoints ==============


@router.get("/projects")
async def list_projects(user: User = Depends(require_permission("wiki", "view"))):
    """List all connected GitHub repo projects."""
    _, ws_id = workspace_context(user, "wiki")
    projects = await async_github_repo_project_manager.list_projects(ws_id)
    return {"projects": projects}


@router.post("/projects")
async def create_project(
    data: GitHubProjectCreate,
    user: User = Depends(require_permission("wiki", "edit")),
):
    """Connect a GitHub repository as a knowledge base collection.

    Clones the repo, converts files to markdown, and indexes them.
    """
    _, ws_id = workspace_context(user, "wiki")

    # Validate owner/repo format
    if not re.match(r"^[\w\-\.]+$", data.github_owner):
        raise HTTPException(status_code=400, detail="Invalid GitHub owner")
    if not re.match(r"^[\w\-\.]+$", data.github_repo):
        raise HTTPException(status_code=400, detail="Invalid GitHub repo name")

    # Check for duplicate
    existing = await async_github_repo_project_manager.get_by_repo(
        data.github_owner, data.github_repo
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Repository {data.github_owner}/{data.github_repo} is already connected",
        )

    # 1. Create collection
    slug = f"github-{data.github_owner}-{data.github_repo}".lower()
    rag_dir = get_rag_dir(data.github_owner, data.github_repo)
    collection = await async_knowledge_collection_manager.create(
        name=data.name,
        slug=slug,
        description=f"GitHub: {data.github_owner}/{data.github_repo} ({data.branch})",
        enabled=True,
        base_dir=str(rag_dir),
    )
    collection_id = collection["id"]

    # 2. Create project record
    create_kwargs: dict = {
        "name": data.name,
        "github_owner": data.github_owner,
        "github_repo": data.github_repo,
        "github_token": data.github_token or None,
        "branch": data.branch,
        "collection_id": collection_id,
        "sync_status": "syncing",
        "workspace_id": ws_id or 1,
    }
    if data.include_patterns is not None:
        create_kwargs["include_patterns"] = json.dumps(data.include_patterns)
    if data.exclude_patterns is not None:
        create_kwargs["exclude_patterns"] = json.dumps(data.exclude_patterns)

    project_dict = await async_github_repo_project_manager.create_project(**create_kwargs)
    project_id = project_dict["id"]

    # 3. Clone and sync
    try:
        commit_sha = clone_repo(data.github_owner, data.github_repo, data.branch, data.github_token)

        include = data.include_patterns or project_dict["include_patterns"]
        exclude = data.exclude_patterns or project_dict["exclude_patterns"]
        documents = build_repo_documents(data.github_owner, data.github_repo, include, exclude)

        total_size = write_rag_documents(data.github_owner, data.github_repo, documents)

        # Write summary
        summary = build_repo_summary(
            data.github_owner, data.github_repo, data.branch, len(documents), total_size
        )
        summary_path = rag_dir / "_summary.md"
        rag_dir.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(summary, encoding="utf-8")

        # 4. Create knowledge document records
        for filename, title, content, _file_size in documents:
            sections = len(re.findall(r"^#{2,3}\s+.+$", content, re.MULTILINE))
            await async_knowledge_doc_manager.create(
                filename=filename,
                title=title,
                source_type="github",
                file_size_bytes=len(content.encode("utf-8")),
                section_count=sections,
                collection_id=collection_id,
            )

        # Summary doc
        summary_fname = f"{data.github_owner}-{data.github_repo}--_summary.md"
        await async_knowledge_doc_manager.create(
            filename=summary_fname,
            title=f"GitHub: {data.github_owner}/{data.github_repo}",
            source_type="github",
            file_size_bytes=len(summary.encode("utf-8")),
            section_count=0,
            collection_id=collection_id,
        )

        # 5. Reload RAG index
        _reload_collection_index(collection_id, documents, rag_dir)

        # 6. Update sync status
        await async_github_repo_project_manager.update_sync_status(
            project_id,
            status="idle",
            commit_sha=commit_sha,
            file_count=len(documents),
            total_size=total_size,
        )

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        logger.error(f"Git clone failed for {data.github_owner}/{data.github_repo}: {error_msg}")
        await async_github_repo_project_manager.update_sync_status(
            project_id, status="error", error=error_msg
        )
        raise HTTPException(status_code=502, detail=f"Git clone failed: {error_msg}")
    except Exception as e:
        logger.error(f"Sync failed for {data.github_owner}/{data.github_repo}: {e}")
        await async_github_repo_project_manager.update_sync_status(
            project_id, status="error", error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")

    await async_audit_logger.log(
        action="create",
        resource="github_repo_project",
        user_id=user.username,
        details={
            "project_id": project_id,
            "repo": f"{data.github_owner}/{data.github_repo}",
            "files": len(documents),
        },
    )

    return {
        "status": "ok",
        "project": (await async_github_repo_project_manager.list_projects(ws_id))[0]
        if len(await async_github_repo_project_manager.list_projects(ws_id)) == 1
        else project_dict,
        "files_indexed": len(documents),
        "collection_id": collection_id,
    }


@router.get("/projects/{project_id}")
async def get_project(
    project_id: int,
    user: User = Depends(require_permission("wiki", "view")),
):
    """Get project details."""
    _, ws_id = workspace_context(user, "wiki")
    projects = await async_github_repo_project_manager.list_projects(ws_id)
    project = next((p for p in projects if p["id"] == project_id), None)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project": project}


@router.put("/projects/{project_id}")
async def update_project(
    project_id: int,
    data: GitHubProjectUpdate,
    user: User = Depends(require_permission("wiki", "edit")),
):
    """Update project settings."""
    _, ws_id = workspace_context(user, "wiki")

    kwargs: dict = {}
    if data.name is not None:
        kwargs["name"] = data.name
    if data.github_token is not None:
        kwargs["github_token"] = data.github_token or None
    if data.branch is not None:
        kwargs["branch"] = data.branch
    if data.include_patterns is not None:
        kwargs["include_patterns"] = json.dumps(data.include_patterns)
    if data.exclude_patterns is not None:
        kwargs["exclude_patterns"] = json.dumps(data.exclude_patterns)

    if not kwargs:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await async_github_repo_project_manager.update_project(project_id, ws_id, **kwargs)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")

    await async_audit_logger.log(
        action="update",
        resource="github_repo_project",
        user_id=user.username,
        details={"project_id": project_id, "fields": list(kwargs.keys())},
    )

    return {"status": "ok", "project": result}


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: int,
    user: User = Depends(require_permission("wiki", "manage")),
):
    """Disconnect a GitHub repository — deletes clone, RAG files, and collection."""
    _, ws_id = workspace_context(user, "wiki")

    # Get project details before deletion
    projects = await async_github_repo_project_manager.list_projects(ws_id)
    project = next((p for p in projects if p["id"] == project_id), None)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    collection_id = project.get("collection_id")

    # Delete knowledge documents and collection
    if collection_id:
        docs = await async_knowledge_doc_manager.get_by_collection(collection_id)
        for doc in docs:
            await async_knowledge_doc_manager.delete(doc["id"])

        # Clear RAG index
        from app.dependencies import get_container

        container = get_container()
        wiki_rag = container.wiki_rag_service
        if wiki_rag:
            rag_dir = get_rag_dir(project["github_owner"], project["github_repo"])
            wiki_rag.reload_collection(collection_id, [], rag_dir)

        await async_knowledge_collection_manager.delete(collection_id)

    # Delete clone
    clean_repo_files(project["github_owner"], project["github_repo"])

    # Delete project record
    await async_github_repo_project_manager.delete_project(project_id, ws_id)

    await async_audit_logger.log(
        action="delete",
        resource="github_repo_project",
        user_id=user.username,
        details={
            "project_id": project_id,
            "repo": f"{project['github_owner']}/{project['github_repo']}",
        },
    )

    return {"status": "ok"}


@router.post("/projects/{project_id}/sync")
async def sync_project(
    project_id: int,
    user: User = Depends(require_permission("wiki", "edit")),
):
    """Re-sync a connected repository (git pull + re-index)."""
    _, ws_id = workspace_context(user, "wiki")

    # Get project with ORM object for token access
    project_orm = await async_github_repo_project_manager.get_project(project_id, ws_id)
    if not project_orm:
        raise HTTPException(status_code=404, detail="Project not found")

    if project_orm.sync_status == "syncing":
        raise HTTPException(status_code=409, detail="Sync already in progress")

    await async_github_repo_project_manager.update_sync_status(project_id, status="syncing")

    try:
        # Pull latest
        new_sha = pull_repo(
            project_orm.github_owner,
            project_orm.github_repo,
            project_orm.github_token,
        )

        # Check if anything changed
        if new_sha == project_orm.last_commit_sha:
            await async_github_repo_project_manager.update_sync_status(
                project_id, status="idle", commit_sha=new_sha
            )
            return {
                "status": "ok",
                "changed": False,
                "commit_sha": new_sha,
                "message": "Already up to date",
            }

        # Rebuild documents
        include = project_orm.get_include_patterns()
        exclude = project_orm.get_exclude_patterns()
        documents = build_repo_documents(
            project_orm.github_owner, project_orm.github_repo, include, exclude
        )

        total_size = write_rag_documents(
            project_orm.github_owner, project_orm.github_repo, documents
        )

        # Write summary
        rag_dir = get_rag_dir(project_orm.github_owner, project_orm.github_repo)
        summary = build_repo_summary(
            project_orm.github_owner,
            project_orm.github_repo,
            project_orm.branch,
            len(documents),
            total_size,
        )
        (rag_dir / "_summary.md").write_text(summary, encoding="utf-8")

        # Update knowledge documents
        collection_id = project_orm.collection_id
        if collection_id:
            existing_docs = await async_knowledge_doc_manager.get_by_collection(collection_id)
            for doc in existing_docs:
                await async_knowledge_doc_manager.delete(doc["id"])

            for filename, title, content, _file_size in documents:
                sections = len(re.findall(r"^#{2,3}\s+.+$", content, re.MULTILINE))
                await async_knowledge_doc_manager.create(
                    filename=filename,
                    title=title,
                    source_type="github",
                    file_size_bytes=len(content.encode("utf-8")),
                    section_count=sections,
                    collection_id=collection_id,
                )

            summary_filename = f"{project_orm.github_owner}-{project_orm.github_repo}--_summary.md"
            await async_knowledge_doc_manager.create(
                filename=summary_filename,
                title=f"GitHub: {project_orm.github_owner}/{project_orm.github_repo}",
                source_type="github",
                file_size_bytes=len(summary.encode("utf-8")),
                section_count=0,
                collection_id=collection_id,
            )

            # Reload RAG index
            _reload_collection_index(collection_id, documents, rag_dir)

        # Update status
        await async_github_repo_project_manager.update_sync_status(
            project_id,
            status="idle",
            commit_sha=new_sha,
            file_count=len(documents),
            total_size=total_size,
        )

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        logger.error(
            f"Git pull failed for {project_orm.github_owner}/{project_orm.github_repo}: {error_msg}"
        )
        await async_github_repo_project_manager.update_sync_status(
            project_id, status="error", error=error_msg
        )
        raise HTTPException(status_code=502, detail=f"Git pull failed: {error_msg}")
    except Exception as e:
        logger.error(f"Sync failed for {project_orm.github_owner}/{project_orm.github_repo}: {e}")
        await async_github_repo_project_manager.update_sync_status(
            project_id, status="error", error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")

    sync_time = datetime.utcnow().strftime("%d.%m.%Y %H:%M")

    await async_audit_logger.log(
        action="sync",
        resource="github_repo_project",
        user_id=user.username,
        details={
            "project_id": project_id,
            "repo": f"{project_orm.github_owner}/{project_orm.github_repo}",
            "files": len(documents),
            "commit_sha": new_sha,
        },
    )

    return {
        "status": "ok",
        "changed": True,
        "commit_sha": new_sha,
        "files_indexed": len(documents),
        "total_size_bytes": total_size,
        "synced_at": sync_time,
    }


@router.get("/projects/{project_id}/status")
async def get_project_status(
    project_id: int,
    user: User = Depends(require_permission("wiki", "view")),
):
    """Get sync status for a project."""
    _, ws_id = workspace_context(user, "wiki")
    projects = await async_github_repo_project_manager.list_projects(ws_id)
    project = next((p for p in projects if p["id"] == project_id), None)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return {
        "sync_status": project["sync_status"],
        "sync_error": project["sync_error"],
        "last_synced": project["last_synced"],
        "last_commit_sha": project["last_commit_sha"],
        "file_count": project["file_count"],
        "total_size_bytes": project["total_size_bytes"],
    }


# ============== Helpers ==============


def _reload_collection_index(
    collection_id: int,
    documents: list[tuple[str, str, str, int]],
    rag_dir,
) -> None:
    """Reload WikiRAG index for a collection."""
    from app.dependencies import get_container

    container = get_container()
    wiki_rag = container.wiki_rag_service
    if wiki_rag:
        filenames = [f[0] for f in documents] + ["_summary.md"]
        wiki_rag.reload_collection(collection_id, filenames, rag_dir)
