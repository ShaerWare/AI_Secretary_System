"""Log viewing endpoints.

List, read, and stream application logs.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from auth_manager import User, require_permission
from service_manager import get_service_manager


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/logs", tags=["logs"])


@router.get("")
async def admin_list_logs():
    """Список доступных логов"""
    manager = get_service_manager()
    return {"logs": manager.get_available_logs()}


@router.get("/{logfile}")
async def admin_read_log(
    logfile: str, lines: int = 100, offset: int = 0, search: Optional[str] = None
):
    """Прочитать лог файл"""
    manager = get_service_manager()
    return manager.read_log(logfile, lines=lines, offset=offset, search=search)


@router.get("/stream/{logfile}")
async def admin_stream_log(
    logfile: str,
    user: User = Depends(require_permission("system", "view")),
):
    """SSE streaming логов"""
    manager = get_service_manager()

    async def generate():
        async for data in manager.stream_log(logfile):
            yield f"data: {data}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
