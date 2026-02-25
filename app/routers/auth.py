# app/routers/auth.py
"""Authentication router - login, user info, auth status, profile management, session management."""

import os

from fastapi import APIRouter, Depends, HTTPException, Request

from app.rate_limiter import RATE_LIMIT_AUTH, limiter
from auth_manager import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    UpdateProfileRequest,
    User,
    authenticate_user,
    create_session,
    get_auth_status,
    get_current_user,
    get_user_permissions,
    require_permission,
    revoke_session,
)
from db.integration import async_audit_logger, async_session_manager, async_user_manager


router = APIRouter(prefix="/admin/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
@limiter.limit(RATE_LIMIT_AUTH)
async def admin_login(request: Request, login_request: LoginRequest):
    """Authenticate user and return JWT token with session tracking."""
    user = await authenticate_user(login_request.username, login_request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    response = await create_session(
        username=user.username,
        role=user.role,
        user_id=user.id,
        ip=ip,
        user_agent=user_agent,
        workspace_id=1,
    )

    # Audit log
    await async_audit_logger.log(
        action="login", resource="auth", user_id=user.username, details={"role": user.role}
    )

    return response


@router.get("/me")
async def admin_get_current_user(user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    deployment_mode = os.getenv("DEPLOYMENT_MODE", "full").lower()
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "workspace_id": user.workspace_id,
        "deployment_mode": deployment_mode,
    }


@router.get("/profile")
async def admin_get_profile(user: User = Depends(get_current_user)):
    """Get full user profile."""
    user_data = await async_user_manager.get_by_id(user.id)
    if not user_data:
        return {"id": user.id, "username": user.username, "role": user.role}
    return {
        "id": user_data["id"],
        "username": user_data["username"],
        "role": user_data["role"],
        "display_name": user_data.get("display_name"),
        "created": user_data.get("created"),
        "last_login": user_data.get("last_login"),
    }


@router.put("/profile")
async def admin_update_profile(
    request: UpdateProfileRequest,
    user: User = Depends(require_permission("settings", "edit")),
):
    """Update user profile (display name)."""
    result = await async_user_manager.update_profile(user.id, display_name=request.display_name)
    if not result:
        raise HTTPException(status_code=404, detail="User not found")

    await async_audit_logger.log(action="update", resource="profile", user_id=user.username)
    return result


@router.post("/change-password")
@limiter.limit(RATE_LIMIT_AUTH)
async def admin_change_password(
    http_request: Request,
    request: ChangePasswordRequest,
    user: User = Depends(require_permission("settings", "edit")),
):
    """Change current user's password. Revokes all sessions and issues a new token."""
    # Verify old password
    auth_result = await authenticate_user(user.username, request.old_password)
    if not auth_result:
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    # Update password (this also revokes all sessions via hook)
    success = await async_user_manager.update_password(user.id, request.new_password)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update password")

    # Create a fresh session for the current user (re-login)
    ip = http_request.client.host if http_request.client else None
    user_agent = http_request.headers.get("user-agent")
    new_login = await create_session(
        username=user.username,
        role=user.role,
        user_id=user.id,
        ip=ip,
        user_agent=user_agent,
        workspace_id=user.workspace_id,
    )

    await async_audit_logger.log(action="update", resource="password", user_id=user.username)
    return {
        "message": "Password updated successfully",
        "access_token": new_login.access_token,
        "token_type": new_login.token_type,
        "expires_in": new_login.expires_in,
    }


@router.get("/sessions")
async def list_sessions(user: User = Depends(get_current_user)):
    """List active sessions for the current user."""
    sessions = await async_session_manager.get_active_for_user(user.id)
    return sessions


@router.delete("/sessions/{jti}")
async def delete_session(
    jti: str,
    user: User = Depends(get_current_user),
):
    """Revoke a specific session. Users can revoke their own sessions; admins can revoke any."""
    # Load permissions for inline check
    user.permissions = await get_user_permissions(user)
    # Check ownership: non-manage users can only revoke their own sessions
    from auth_manager import level_gte

    if not level_gte(user.permissions.get("users", ""), "manage"):
        db_session = await async_session_manager.get_by_jti(jti)
        if db_session is None or db_session.user_id != user.id:
            raise HTTPException(status_code=404, detail="Session not found")

    revoked = await revoke_session(jti)
    if not revoked:
        raise HTTPException(status_code=404, detail="Session not found or already revoked")

    await async_audit_logger.log(
        action="revoke", resource="session", user_id=user.username, details={"jti": jti}
    )
    return {"message": "Session revoked"}


@router.get("/permissions")
async def get_permissions(user: User = Depends(get_current_user)):
    """Get effective permissions for the current user."""
    permissions = await get_user_permissions(user)

    # Filter out modules unavailable in cloud mode
    deployment_mode = os.getenv("DEPLOYMENT_MODE", "full").lower()
    if deployment_mode == "cloud":
        for module in ("speech", "gsm", "system"):
            permissions.pop(module, None)

    return permissions


@router.get("/status")
async def admin_auth_status():
    """Get authentication configuration status."""
    return get_auth_status()
