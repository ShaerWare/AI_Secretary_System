"""Client cards (`/admin/clients/*`): what the assistant remembers about a client.

RBAC module ``sales``, like the rest of the CRM page: the cards hold personal
data and are seen by the same people who see the deals.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.dependencies import get_container
from auth_manager import User, require_permission
from modules.clients.service import ClientMemoryError, client_memory_service
from modules.monitoring.service import audit_service


router = APIRouter(prefix="/admin/clients", tags=["clients"])


class SettingsRequest(BaseModel):
    instances: Optional[dict[str, bool]] = None
    idle_minutes: Optional[int] = None


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    manager_notes: Optional[str] = None
    card_md: Optional[str] = None


class RefreshRequest(BaseModel):
    session_id: str


def _http(e: ClientMemoryError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=str(e))


async def _audit(action: str, user: User, profile_id: Any, details: Optional[dict] = None):
    await audit_service.log(
        action=action,
        resource="client_profile",
        resource_id=str(profile_id),
        user_id=user.username,
        details=details,
    )


@router.get("/settings")
async def clients_settings(user: User = Depends(require_permission("sales", "view"))):
    return await client_memory_service.get_settings()


@router.put("/settings")
async def clients_save_settings(
    req: SettingsRequest, user: User = Depends(require_permission("sales", "edit"))
):
    try:
        settings = await client_memory_service.save_settings(req.model_dump())
    except ClientMemoryError as e:
        raise _http(e) from e
    await _audit("settings", user, "client_memory", settings)
    return settings


@router.get("")
async def clients_list(
    q: str = "",
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(require_permission("sales", "view")),
):
    return {"profiles": await client_memory_service.list_profiles(user.workspace_id, q, limit)}


@router.get("/{profile_id}")
async def clients_get(profile_id: int, user: User = Depends(require_permission("sales", "view"))):
    try:
        return await client_memory_service.get_profile(profile_id, user.workspace_id)
    except ClientMemoryError as e:
        raise _http(e) from e


@router.put("/{profile_id}")
async def clients_update(
    profile_id: int, req: ProfileUpdate, user: User = Depends(require_permission("sales", "edit"))
):
    try:
        profile = await client_memory_service.update_profile(
            profile_id, user.workspace_id, req.model_dump()
        )
    except ClientMemoryError as e:
        raise _http(e) from e
    await _audit("update", user, profile_id)
    return profile


@router.delete("/{profile_id}")
async def clients_delete(
    profile_id: int, user: User = Depends(require_permission("sales", "edit"))
):
    try:
        await client_memory_service.delete_profile(profile_id, user.workspace_id)
    except ClientMemoryError as e:
        raise _http(e) from e
    await _audit("delete", user, profile_id)
    return {"status": "ok"}


@router.post("/refresh")
async def clients_refresh(
    req: RefreshRequest, user: User = Depends(require_permission("sales", "edit"))
):
    """Fold a dialogue into its client's card now, without waiting for the task."""
    try:
        profile = await client_memory_service.update_from_session(
            req.session_id, get_container().llm_service
        )
    except ClientMemoryError as e:
        raise _http(e) from e
    if profile is None:
        raise HTTPException(status_code=409, detail="Новых сообщений нет или LLM не ответила")
    await _audit("refresh", user, profile["id"], {"session_id": req.session_id})
    return profile
