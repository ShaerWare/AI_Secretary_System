"""Workspace management API — members, info."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth_manager import (
    User,
    _member_role_cache,
    require_permission,
    revoke_all_user_sessions,
)
from db.integration import (
    async_audit_logger,
    async_role_manager,
    async_workspace_manager,
)


router = APIRouter(prefix="/admin/workspace", tags=["workspace"])


# ============== Schemas ==============


class MemberRoleUpdate(BaseModel):
    role_name: str = Field(..., min_length=1, max_length=50)


# ============== Workspace Info ==============


@router.get("")
async def get_workspace_info(
    user: User = Depends(require_permission("users", "view")),
):
    """Get current workspace info."""
    info = await async_workspace_manager.get_workspace_info(user.workspace_id)
    if not info:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return info


# ============== Members ==============


@router.get("/members")
async def list_members(
    user: User = Depends(require_permission("users", "view")),
):
    """List all members of the current workspace."""
    return await async_workspace_manager.list_members(user.workspace_id)


@router.put("/members/{user_id}/role")
async def update_member_role(
    user_id: int,
    body: MemberRoleUpdate,
    user: User = Depends(require_permission("users", "manage")),
):
    """Change a workspace member's role."""
    ws_id = user.workspace_id

    # Cannot change own role
    if user_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    # Cannot change workspace owner's role
    owner_id = await async_workspace_manager.get_workspace_owner_id(ws_id)
    if user_id == owner_id:
        raise HTTPException(status_code=400, detail="Cannot change the workspace owner's role")

    # Validate role exists
    role = await async_role_manager.get_by_name(body.role_name)
    if not role:
        raise HTTPException(status_code=400, detail=f"Role '{body.role_name}' does not exist")

    result = await async_workspace_manager.update_member_role(ws_id, user_id, body.role_name)
    if not result:
        raise HTTPException(status_code=404, detail="Member not found")

    # Invalidate cached permissions
    _member_role_cache.invalidate_user(user_id)

    await async_audit_logger.log(
        action="update",
        resource="workspace_member",
        user_id=user.username,
        details={"target_user_id": user_id, "new_role": body.role_name},
    )
    return result


@router.delete("/members/{user_id}")
async def remove_member(
    user_id: int,
    user: User = Depends(require_permission("users", "manage")),
):
    """Remove a member from the workspace."""
    ws_id = user.workspace_id

    # Cannot remove self
    if user_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    # Cannot remove workspace owner
    owner_id = await async_workspace_manager.get_workspace_owner_id(ws_id)
    if user_id == owner_id:
        raise HTTPException(status_code=400, detail="Cannot remove the workspace owner")

    removed = await async_workspace_manager.remove_member(ws_id, user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Member not found")

    # Revoke sessions and clear cache
    _member_role_cache.invalidate_user(user_id)
    try:
        await revoke_all_user_sessions(user_id)
    except Exception:
        pass  # best-effort

    await async_audit_logger.log(
        action="delete",
        resource="workspace_member",
        user_id=user.username,
        details={"target_user_id": user_id},
    )
    return {"message": "Member removed"}
