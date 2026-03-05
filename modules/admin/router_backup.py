"""Backup and restore router for system data management."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services.backup_service import get_backup_service
from auth_manager import User, require_permission


router = APIRouter(prefix="/admin/backup", tags=["backup"])


# ============== Pydantic Models ==============


class CreateBackupRequest(BaseModel):
    """Request model for creating a backup."""

    include_voices: bool = False
    include_adapters: bool = False
    description: str = ""


class RestoreBackupRequest(BaseModel):
    """Request model for restoring a backup."""

    filename: str
    restore_database: bool = True
    restore_voices: bool = False
    restore_adapters: bool = False


class BackupResponse(BaseModel):
    """Response model for backup operations."""

    filename: str
    size: int
    created_at: Optional[str] = None
    description: str = ""
    includes: dict = {}
    file_count: int = 0


# ============== Endpoints ==============


@router.get("/system-info")
async def get_system_info(_: User = Depends(require_permission("system", "view"))) -> dict:
    """
    Get system info for backup planning.

    Returns database size, voice files size, adapters size, and backup stats.
    """
    service = get_backup_service()
    return service.get_system_info()


@router.get("/list")
async def list_backups(_: User = Depends(require_permission("system", "view"))) -> list[dict]:
    """
    List all available backups.

    Returns list of backups with metadata (size, date, contents).
    """
    service = get_backup_service()
    return service.list_backups()


@router.get("/{filename}")
async def get_backup_info(
    filename: str, _: User = Depends(require_permission("system", "view"))
) -> dict:
    """
    Get detailed info about a specific backup.

    Args:
        filename: Backup filename (e.g., backup_20260205_120000.zip)
    """
    service = get_backup_service()
    info = service.get_backup_info(filename)
    if not info:
        raise HTTPException(status_code=404, detail="Backup not found")
    return info


@router.get("/{filename}/download")
async def download_backup(
    filename: str, _: User = Depends(require_permission("system", "view"))
) -> FileResponse:
    """
    Download a backup file.

    Args:
        filename: Backup filename (e.g., backup_20260205_120000.zip)
    """
    service = get_backup_service()
    backup_path = service.get_backup_path(filename)
    if not backup_path:
        raise HTTPException(status_code=404, detail="Backup not found")

    return FileResponse(
        path=backup_path,
        filename=filename,
        media_type="application/zip",
    )


@router.post("/{filename}/validate")
async def validate_backup(
    filename: str, _: User = Depends(require_permission("system", "edit"))
) -> dict:
    """
    Validate backup integrity by checking checksums.

    Args:
        filename: Backup filename to validate
    """
    service = get_backup_service()
    return service.validate_backup(filename)


@router.post("/create")
async def create_backup(
    request: CreateBackupRequest, _: User = Depends(require_permission("system", "manage"))
) -> dict:
    """
    Create a new backup.

    Options:
    - include_voices: Include voice sample WAV files
    - include_adapters: Include LoRA adapter files
    - description: Optional description for the backup
    """
    service = get_backup_service()
    return service.create_backup(
        include_voices=request.include_voices,
        include_adapters=request.include_adapters,
        description=request.description,
    )


@router.post("/restore")
async def restore_backup(
    request: RestoreBackupRequest, _: User = Depends(require_permission("system", "manage"))
) -> dict:
    """
    Restore from a backup.

    WARNING: This will overwrite existing data!

    Options:
    - restore_database: Restore SQLite database (creates .bak of current)
    - restore_voices: Restore voice sample files
    - restore_adapters: Restore LoRA adapter files
    """
    service = get_backup_service()
    result = service.restore_backup(
        filename=request.filename,
        restore_database=request.restore_database,
        restore_voices=request.restore_voices,
        restore_adapters=request.restore_adapters,
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Restore failed"),
        )
    return result


@router.delete("/{filename}")
async def delete_backup(
    filename: str, _: User = Depends(require_permission("system", "manage"))
) -> dict:
    """
    Delete a backup file.

    Args:
        filename: Backup filename to delete
    """
    service = get_backup_service()
    result = service.delete_backup(filename)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result
