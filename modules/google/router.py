"""Google OAuth router — auth flow, status, disconnect."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from auth_manager import User, get_current_user
from modules.google.service import google_oauth_service


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/google", tags=["google"])

# Callback router (no auth — browser redirect from Google)
callback_router = APIRouter(tags=["google-oauth"])


@router.get("/auth-url")
async def google_auth_url(user: User = Depends(get_current_user)):
    """Generate Google OAuth consent URL."""
    try:
        url = google_oauth_service.build_auth_url(user.id)
        return {"auth_url": url}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def google_status(user: User = Depends(get_current_user)):
    """Check Google connection status for current user."""
    return await google_oauth_service.get_status(user.id)


@router.post("/disconnect")
async def google_disconnect(user: User = Depends(get_current_user)):
    """Disconnect Google account."""
    result = await google_oauth_service.disconnect(user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Google account not connected")
    return {"status": "ok"}


@callback_router.get("/admin/oauth/google/callback")
async def google_oauth_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
):
    """Google OAuth callback — exchanges code for tokens, redirects to SPA."""
    if error:
        logger.warning(f"Google OAuth error: {error}")
        return RedirectResponse(url="/admin/#/settings?google=error")

    if not code or not state:
        return RedirectResponse(url="/admin/#/settings?google=error")

    try:
        result = await google_oauth_service.exchange_code(code, state)
        logger.info(f"Google OAuth success: {result.get('google_email')}")
        return RedirectResponse(url="/admin/#/settings?google=connected")
    except Exception as e:
        logger.error(f"Google OAuth callback error: {e}")
        return RedirectResponse(url="/admin/#/settings?google=error")
