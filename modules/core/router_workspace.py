# modules/core/router_workspace.py
"""Workspace management API — members, invites."""

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.rate_limiter import limit_auth
from auth_manager import (
    User,
    create_session,
    require_permission,
)
from modules.core.service import role_service, user_service, workspace_service
from modules.monitoring.service import audit_service


router = APIRouter(prefix="/admin/workspace", tags=["workspace"])

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.\-]+$")


# ============== Schemas ==============


class MemberRoleUpdate(BaseModel):
    role_name: str = Field(..., min_length=1, max_length=50)


class InviteCreate(BaseModel):
    role_name: str = Field(..., min_length=1, max_length=50)
    email: str | None = None
    max_uses: int | None = Field(None, ge=1)
    expires_hours: int | None = Field(None, ge=1, le=8760)


class InviteAccept(BaseModel):
    invite_code: str = Field(..., min_length=1)
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)
    display_name: str | None = Field(None, max_length=100)


# ============== Workspace Info ==============


@router.get("")
async def get_workspace_info(
    user: User = Depends(require_permission("users", "view")),
):
    """Get current workspace info."""
    info = await workspace_service.get_workspace_info(user.workspace_id)
    if not info:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return info


# ============== Members ==============


@router.get("/members")
async def list_members(
    user: User = Depends(require_permission("users", "view")),
):
    """List all members of the current workspace."""
    return await workspace_service.list_members(user.workspace_id)


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
    owner_id = await workspace_service.get_workspace_owner_id(ws_id)
    if user_id == owner_id:
        raise HTTPException(status_code=400, detail="Cannot change the workspace owner's role")

    # Validate role exists
    role = await role_service.get_by_name(body.role_name)
    if not role:
        raise HTTPException(status_code=400, detail=f"Role '{body.role_name}' does not exist")

    result = await workspace_service.update_member_role(ws_id, user_id, body.role_name)
    if not result:
        raise HTTPException(status_code=404, detail="Member not found")

    await audit_service.log(
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
    owner_id = await workspace_service.get_workspace_owner_id(ws_id)
    if user_id == owner_id:
        raise HTTPException(status_code=400, detail="Cannot remove the workspace owner")

    removed = await workspace_service.remove_member(ws_id, user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Member not found")

    await audit_service.log(
        action="delete",
        resource="workspace_member",
        user_id=user.username,
        details={"target_user_id": user_id},
    )
    return {"message": "Member removed"}


# ============== Invites ==============


@router.post("/invites")
async def create_invite(
    body: InviteCreate,
    user: User = Depends(require_permission("users", "manage")),
):
    """Create an invite link for the workspace."""
    # Cannot invite with owner role
    if body.role_name == "owner":
        raise HTTPException(status_code=400, detail="Cannot create invite with 'owner' role")

    # Validate role exists
    role = await role_service.get_by_name(body.role_name)
    if not role:
        raise HTTPException(status_code=400, detail=f"Role '{body.role_name}' does not exist")

    invite = await workspace_service.create_invite(
        workspace_id=user.workspace_id,
        role_name=body.role_name,
        created_by=user.id,
        email=body.email,
        max_uses=body.max_uses,
        expires_hours=body.expires_hours,
    )

    await audit_service.log(
        action="create",
        resource="workspace_invite",
        user_id=user.username,
        details={"role_name": body.role_name, "invite_id": invite["id"]},
    )
    return invite


@router.get("/invites")
async def list_invites(
    user: User = Depends(require_permission("users", "manage")),
):
    """List all invites for the current workspace."""
    return await workspace_service.list_invites(user.workspace_id)


@router.delete("/invites/{invite_id}")
async def delete_invite(
    invite_id: int,
    user: User = Depends(require_permission("users", "manage")),
):
    """Delete an invite."""
    deleted = await workspace_service.delete_invite(user.workspace_id, invite_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Invite not found")

    await audit_service.log(
        action="delete",
        resource="workspace_invite",
        user_id=user.username,
        details={"invite_id": invite_id},
    )
    return {"message": "Invite deleted"}


@router.get("/invites/{invite_code}/info")
async def get_invite_info(invite_code: str):
    """Public endpoint: get basic invite info for the accept page."""
    info = await workspace_service.get_invite_info(invite_code)
    if not info:
        raise HTTPException(status_code=404, detail="Invite not found or expired")
    return info


@router.post("/invites/accept")
@limit_auth
async def accept_invite(body: InviteAccept, request: Request):
    """Public endpoint: register via invite link."""
    # Validate username format
    if not USERNAME_RE.match(body.username):
        raise HTTPException(
            status_code=400,
            detail="Username must contain only letters, digits, underscores, dots, and hyphens",
        )

    # Check username not taken
    existing = await user_service.get_by_username(body.username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")

    # Accept invite (create user + membership)
    result = await workspace_service.accept_invite(
        invite_code=body.invite_code,
        username=body.username,
        password=body.password,
        display_name=body.display_name,
    )
    if not result:
        raise HTTPException(status_code=400, detail="Invite is invalid or expired")

    # Auto-login: create session and return JWT
    user_data = result["user"]
    login_resp = await create_session(
        username=user_data["username"],
        role=user_data["role"],
        user_id=user_data["id"],
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        workspace_id=result["workspace_id"],
    )

    await audit_service.log(
        action="create",
        resource="user_via_invite",
        user_id=user_data["username"],
        details={"workspace_id": result["workspace_id"], "role_name": result["role_name"]},
    )

    return {
        "access_token": login_resp.access_token,
        "token_type": login_resp.token_type,
        "expires_in": login_resp.expires_in,
        "user": user_data,
    }
