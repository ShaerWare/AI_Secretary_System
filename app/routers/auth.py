# app/routers/auth.py
"""Authentication router - login, user info, auth status."""

from fastapi import APIRouter, Depends, HTTPException

from auth_manager import (
    LoginRequest,
    LoginResponse,
    User,
    authenticate_user,
    create_access_token,
    get_auth_status,
    get_current_user,
)
from db.integration import async_audit_logger


router = APIRouter(prefix="/admin/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def admin_login(request: LoginRequest):
    """
    Authenticate user and return JWT token.

    Default credentials: admin / admin
    Set ADMIN_USERNAME and ADMIN_PASSWORD_HASH env vars for production.
    """
    user = authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token, expires_in = create_access_token(user.username, user.role)

    # Audit log
    await async_audit_logger.log(
        action="login", resource="auth", user_id=user.username, details={"role": user.role}
    )

    return LoginResponse(access_token=token, token_type="bearer", expires_in=expires_in)


@router.get("/me")
async def admin_get_current_user(user: User = Depends(get_current_user)):
    """Get current authenticated user info"""
    return {"username": user.username, "role": user.role}


@router.get("/status")
async def admin_auth_status():
    """Get authentication configuration status"""
    return get_auth_status()
