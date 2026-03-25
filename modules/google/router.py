"""Google OAuth + Drive/Docs/Sheets router."""

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


# ── Drive / Docs / Sheets ────────────────────────────────────


@router.get("/drive/files")
async def drive_list_files(
    folder_id: str = Query("root"),
    query: str = Query(None),
    page_token: str = Query(None),
    page_size: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    """List files in a Google Drive folder."""
    try:
        return await google_oauth_service.drive_list(
            user.id, folder_id, query, page_token, page_size
        )
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(f"Drive list error: {e}")
        raise HTTPException(status_code=502, detail="Google Drive error")


@router.get("/drive/search")
async def drive_search(
    query: str = Query(..., min_length=1),
    page_size: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
):
    """Search files across Google Drive."""
    try:
        return await google_oauth_service.drive_search(user.id, query, page_size)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(f"Drive search error: {e}")
        raise HTTPException(status_code=502, detail="Google Drive error")


@router.get("/drive/file/{file_id}/content")
async def drive_get_content(
    file_id: str,
    mime_type: str = Query(...),
    sheet_name: str = Query(None),
    user: User = Depends(get_current_user),
):
    """Get file content (auto-detects Docs/Sheets/text files)."""
    try:
        if mime_type == "application/vnd.google-apps.spreadsheet" and sheet_name:
            return await google_oauth_service.sheets_get_data(user.id, file_id, sheet_name)
        return await google_oauth_service.drive_get_file_content(user.id, file_id, mime_type)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(f"File content error: {e}")
        raise HTTPException(status_code=502, detail="Google API error")
