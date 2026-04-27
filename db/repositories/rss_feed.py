"""Repository for RSS feeds and their persisted items (used for dedup)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import RSSFeed, RSSFeedItem
from db.repositories.base import BaseRepository


class RSSFeedRepository(BaseRepository[RSSFeed]):
    """RSS feed CRUD."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, RSSFeed)

    async def list_feeds(
        self,
        workspace_id: Optional[int] = None,
        collection_id: Optional[int] = None,
    ) -> list[dict]:
        query = select(RSSFeed).order_by(RSSFeed.name)
        query = self._apply_workspace_filter(query, workspace_id)
        if collection_id is not None:
            query = query.where(RSSFeed.collection_id == collection_id)
        result = await self.session.execute(query)
        return [f.to_dict() for f in result.scalars().all()]

    async def list_feed_orms(self, enabled_only: bool = True) -> list[RSSFeed]:
        """For background sync — return ORM objects (no workspace filter)."""
        query = select(RSSFeed)
        if enabled_only:
            query = query.where(RSSFeed.enabled.is_(True))
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_feed(self, feed_id: int, workspace_id: Optional[int] = None) -> Optional[RSSFeed]:
        if workspace_id is not None:
            query = select(RSSFeed).where(RSSFeed.id == feed_id)
            query = self._apply_workspace_filter(query, workspace_id)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        return await self.session.get(RSSFeed, feed_id)

    async def get_by_url(self, url: str) -> Optional[RSSFeed]:
        result = await self.session.execute(select(RSSFeed).where(RSSFeed.url == url))
        return result.scalar_one_or_none()

    async def create_feed(self, **kwargs) -> RSSFeed:
        feed = RSSFeed(**kwargs)
        self.session.add(feed)
        await self.session.flush()
        return feed

    async def update_feed(
        self, feed_id: int, workspace_id: Optional[int] = None, **kwargs
    ) -> Optional[dict]:
        feed = await self.get_feed(feed_id, workspace_id)
        if not feed:
            return None
        for key, value in kwargs.items():
            if hasattr(feed, key):
                setattr(feed, key, value)
        feed.updated = datetime.utcnow()
        await self.session.flush()
        return feed.to_dict()

    async def update_sync_status(
        self,
        feed_id: int,
        status: str,
        error: Optional[str] = None,
        item_count: Optional[int] = None,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
    ) -> None:
        feed = await self.session.get(RSSFeed, feed_id)
        if not feed:
            return
        feed.sync_status = status
        feed.last_error = error
        if status == "idle" and error is None:
            feed.last_synced = datetime.utcnow()
        if item_count is not None:
            feed.item_count = item_count
        if etag is not None:
            feed.last_etag = etag
        if last_modified is not None:
            feed.last_modified = last_modified
        feed.updated = datetime.utcnow()
        await self.session.flush()

    async def delete_feed(self, feed_id: int, workspace_id: Optional[int] = None) -> bool:
        feed = await self.get_feed(feed_id, workspace_id)
        if not feed:
            return False
        await self.session.delete(feed)
        await self.session.flush()
        return True


class RSSFeedItemRepository(BaseRepository[RSSFeedItem]):
    """Persisted RSS items — primarily used for dedup by (feed_id, guid)."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, RSSFeedItem)

    async def get_known_guids(self, feed_id: int) -> set[str]:
        result = await self.session.execute(
            select(RSSFeedItem.guid).where(RSSFeedItem.feed_id == feed_id)
        )
        return {row[0] for row in result.all()}

    async def add_item(
        self,
        feed_id: int,
        guid: str,
        title: str,
        link: Optional[str],
        document_id: Optional[int],
        pub_date: Optional[datetime],
    ) -> RSSFeedItem:
        item = RSSFeedItem(
            feed_id=feed_id,
            guid=guid,
            title=title,
            link=link,
            document_id=document_id,
            pub_date=pub_date,
        )
        self.session.add(item)
        await self.session.flush()
        return item
