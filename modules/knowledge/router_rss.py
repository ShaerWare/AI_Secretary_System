"""RSS feeds management router — CRUD + manual sync of knowledge RSS feeds."""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth_manager import User, require_permission, workspace_context
from db.database import AsyncSessionLocal
from db.repositories.rss_feed import RSSFeedRepository
from modules.knowledge.rss_service import sync_all_feeds, sync_feed
from modules.knowledge.service import knowledge_collection_service
from modules.monitoring.service import audit_service


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/rss", tags=["rss"])


class RSSFeedCreate(BaseModel):
    name: str
    url: str
    collection_id: int
    fetch_full_text: bool = True
    verify_ssl: bool = True
    enabled: bool = True


class RSSFeedUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    collection_id: Optional[int] = None
    fetch_full_text: Optional[bool] = None
    verify_ssl: Optional[bool] = None
    enabled: Optional[bool] = None


@router.get("/feeds")
async def list_feeds(
    collection_id: Optional[int] = None,
    user: User = Depends(require_permission("wiki", "view")),
):
    """List all RSS feeds, optionally filtered by collection."""
    _, ws_id = workspace_context(user, "wiki")
    async with AsyncSessionLocal() as session:
        repo = RSSFeedRepository(session)
        feeds = await repo.list_feeds(workspace_id=ws_id, collection_id=collection_id)
    return {"feeds": feeds}


@router.post("/feeds")
async def create_feed(
    data: RSSFeedCreate,
    user: User = Depends(require_permission("wiki", "edit")),
):
    """Create a new RSS feed subscription."""
    _, ws_id = workspace_context(user, "wiki")

    if not data.url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must be http(s)://")

    collection = await knowledge_collection_service.get_by_id(
        data.collection_id, workspace_id=ws_id
    )
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    async with AsyncSessionLocal() as session:
        repo = RSSFeedRepository(session)
        existing = await repo.get_by_url(data.url)
        if existing:
            raise HTTPException(status_code=409, detail="Feed with this URL already exists")
        feed = await repo.create_feed(
            name=data.name,
            url=data.url,
            collection_id=data.collection_id,
            fetch_full_text=data.fetch_full_text,
            verify_ssl=data.verify_ssl,
            enabled=data.enabled,
            workspace_id=ws_id or 1,
        )
        await session.commit()
        feed_dict = feed.to_dict()

    await audit_service.log(
        action="create",
        resource="rss_feed",
        user_id=user.username,
        details={"feed_id": feed_dict["id"], "url": data.url},
    )
    return feed_dict


@router.patch("/feeds/{feed_id}")
async def update_feed(
    feed_id: int,
    data: RSSFeedUpdate,
    user: User = Depends(require_permission("wiki", "edit")),
):
    """Update an RSS feed."""
    _, ws_id = workspace_context(user, "wiki")
    payload = {k: v for k, v in data.model_dump().items() if v is not None}
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")

    async with AsyncSessionLocal() as session:
        repo = RSSFeedRepository(session)
        result = await repo.update_feed(feed_id, workspace_id=ws_id, **payload)
        await session.commit()
    if not result:
        raise HTTPException(status_code=404, detail="Feed not found")
    return result


@router.delete("/feeds/{feed_id}")
async def delete_feed(
    feed_id: int,
    user: User = Depends(require_permission("wiki", "edit")),
):
    """Delete an RSS feed (cascades feed items)."""
    _, ws_id = workspace_context(user, "wiki")
    async with AsyncSessionLocal() as session:
        repo = RSSFeedRepository(session)
        deleted = await repo.delete_feed(feed_id, workspace_id=ws_id)
        await session.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail="Feed not found")
    await audit_service.log(
        action="delete",
        resource="rss_feed",
        user_id=user.username,
        details={"feed_id": feed_id},
    )
    return {"status": "ok"}


@router.post("/feeds/{feed_id}/sync")
async def sync_one_feed(
    feed_id: int,
    user: User = Depends(require_permission("wiki", "edit")),
):
    """Manually sync a single feed in the background."""
    _, ws_id = workspace_context(user, "wiki")
    async with AsyncSessionLocal() as session:
        repo = RSSFeedRepository(session)
        feed = await repo.get_feed(feed_id, workspace_id=ws_id)
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    asyncio.create_task(sync_feed(feed_id))
    return {"status": "scheduled", "feed_id": feed_id}


@router.post("/sync-all")
async def sync_all(_: User = Depends(require_permission("wiki", "edit"))):
    """Trigger sync for ALL enabled feeds (background)."""
    asyncio.create_task(sync_all_feeds())
    return {"status": "scheduled"}


@router.get("/feeds/{feed_id}/items")
async def list_feed_items(
    feed_id: int,
    limit: int = 50,
    user: User = Depends(require_permission("wiki", "view")),
):
    """List recent items ingested from a feed."""
    _, ws_id = workspace_context(user, "wiki")
    async with AsyncSessionLocal() as session:
        repo = RSSFeedRepository(session)
        feed = await repo.get_feed(feed_id, workspace_id=ws_id)
        if not feed:
            raise HTTPException(status_code=404, detail="Feed not found")
        from sqlalchemy import desc, select

        from db.models import RSSFeedItem

        result = await session.execute(
            select(RSSFeedItem)
            .where(RSSFeedItem.feed_id == feed_id)
            .order_by(desc(RSSFeedItem.id))
            .limit(min(max(limit, 1), 200))
        )
        items = [item.to_dict() for item in result.scalars().all()]
    return {"feed_id": feed_id, "items": items}
