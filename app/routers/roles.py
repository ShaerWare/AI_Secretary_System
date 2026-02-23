"""RBAC role management API endpoints."""

from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth_manager import User, invalidate_permissions_cache, require_permission
from db.integration import async_audit_logger, async_role_manager


router = APIRouter(prefix="/admin/roles", tags=["roles"])


# ============== Pydantic Schemas ==============


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    display_name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    permissions: Dict[str, str] = Field(default_factory=dict)


class RoleUpdate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    permissions: Optional[Dict[str, str]] = None


# ============== Endpoints ==============

VALID_LEVELS = {"view", "edit", "manage"}


def _validate_permissions(permissions: Dict[str, str]) -> None:
    """Raise 400 if any permission level is invalid."""
    for module, level in permissions.items():
        if level not in VALID_LEVELS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid level '{level}' for module '{module}'. Must be one of: {', '.join(sorted(VALID_LEVELS))}",
            )


@router.get("")
async def list_roles(user: User = Depends(require_permission("users", "manage"))):
    """List all roles with permissions."""
    roles = await async_role_manager.get_all_with_permissions()
    return roles


@router.post("", status_code=201)
async def create_role(
    body: RoleCreate, user: User = Depends(require_permission("users", "manage"))
):
    """Create a new custom role."""
    if body.permissions:
        _validate_permissions(body.permissions)

    existing = await async_role_manager.get_by_name(body.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Role '{body.name}' already exists")

    role = await async_role_manager.create_role(
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        is_system=False,
        permissions=body.permissions or None,
    )

    await async_audit_logger.log(
        action="create",
        resource="role",
        user_id=user.username,
        details={"role_name": body.name},
    )
    return role


@router.get("/{role_id}")
async def get_role(role_id: int, user: User = Depends(require_permission("users", "manage"))):
    """Get a single role by ID."""
    role = await async_role_manager.get_with_permissions(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


@router.put("/{role_id}")
async def update_role(
    role_id: int, body: RoleUpdate, user: User = Depends(require_permission("users", "manage"))
):
    """Update a role. System roles: can update permissions, cannot change name."""
    if body.permissions is not None:
        _validate_permissions(body.permissions)

    role = await async_role_manager.update_role(
        role_id=role_id,
        display_name=body.display_name,
        description=body.description,
        permissions=body.permissions,
    )
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    invalidate_permissions_cache()

    await async_audit_logger.log(
        action="update",
        resource="role",
        user_id=user.username,
        details={"role_id": role_id},
    )
    return role


@router.delete("/{role_id}")
async def delete_role(role_id: int, user: User = Depends(require_permission("users", "manage"))):
    """Delete a custom role. System roles cannot be deleted."""
    role = await async_role_manager.get_with_permissions(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.get("is_system"):
        raise HTTPException(status_code=400, detail="Cannot delete a system role")

    await async_role_manager.delete_role(role_id)
    invalidate_permissions_cache()

    await async_audit_logger.log(
        action="delete",
        resource="role",
        user_id=user.username,
        details={"role_id": role_id, "role_name": role.get("name")},
    )
    return {"message": "Role deleted"}
