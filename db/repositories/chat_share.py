"""
Repository for managing chat session sharing between users.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ChatSessionShare, User
from db.repositories.base import BaseRepository


class ChatShareRepository(BaseRepository[ChatSessionShare]):
    """Repository for chat session share operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ChatSessionShare)

    async def get_shares_for_session(self, session_id: str) -> List[dict]:
        """Get all shares for a session with user info."""
        result = await self.session.execute(
            select(ChatSessionShare, User.username, User.display_name)
            .join(User, ChatSessionShare.user_id == User.id)
            .where(ChatSessionShare.session_id == session_id)
            .order_by(ChatSessionShare.shared_at.desc())
        )
        rows = result.all()
        return [
            {
                **share.to_dict(),
                "username": username,
                "display_name": display_name,
            }
            for share, username, display_name in rows
        ]

    async def get_share(self, session_id: str, user_id: int) -> Optional[ChatSessionShare]:
        """Get a specific share record."""
        result = await self.session.execute(
            select(ChatSessionShare).where(
                ChatSessionShare.session_id == session_id,
                ChatSessionShare.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_share(
        self,
        session_id: str,
        user_id: int,
        permission: str = "read",
        shared_by: Optional[int] = None,
    ) -> dict:
        """Add or update a share (upsert)."""
        existing = await self.get_share(session_id, user_id)
        if existing:
            existing.permission = permission
            existing.shared_by = shared_by
            existing.shared_at = datetime.utcnow()
            await self.session.commit()
            await self.session.refresh(existing)
            return existing.to_dict()

        share = ChatSessionShare(
            session_id=session_id,
            user_id=user_id,
            permission=permission,
            shared_by=shared_by,
            shared_at=datetime.utcnow(),
        )
        self.session.add(share)
        await self.session.commit()
        await self.session.refresh(share)
        return share.to_dict()

    async def remove_share(self, session_id: str, user_id: int) -> bool:
        """Remove a share."""
        result = await self.session.execute(
            delete(ChatSessionShare).where(
                ChatSessionShare.session_id == session_id,
                ChatSessionShare.user_id == user_id,
            )
        )
        await self.session.commit()
        return bool(result.rowcount > 0)  # type: ignore[attr-defined]

    async def update_permission(self, session_id: str, user_id: int, permission: str) -> bool:
        """Update share permission."""
        result = await self.session.execute(
            update(ChatSessionShare)
            .where(
                ChatSessionShare.session_id == session_id,
                ChatSessionShare.user_id == user_id,
            )
            .values(permission=permission)
        )
        await self.session.commit()
        return bool(result.rowcount > 0)  # type: ignore[attr-defined]

    async def get_shared_session_ids(self, user_id: int) -> List[str]:
        """Get all session IDs shared with a user."""
        result = await self.session.execute(
            select(ChatSessionShare.session_id).where(ChatSessionShare.user_id == user_id)
        )
        return [row[0] for row in result.all()]

    async def get_user_permission(self, session_id: str, user_id: int) -> Optional[str]:
        """Get user's permission for a session (None if not shared)."""
        result = await self.session.execute(
            select(ChatSessionShare.permission).where(
                ChatSessionShare.session_id == session_id,
                ChatSessionShare.user_id == user_id,
            )
        )
        row = result.first()
        return row[0] if row else None

    async def remove_all_shares(self, session_id: str) -> int:
        """Remove all shares for a session."""
        result = await self.session.execute(
            delete(ChatSessionShare).where(ChatSessionShare.session_id == session_id)
        )
        await self.session.commit()
        return int(result.rowcount)  # type: ignore[attr-defined]

    async def get_share_counts(self, session_ids: list[str]) -> dict[str, int]:
        """Get share counts for multiple sessions in a single query."""
        if not session_ids:
            return {}
        result = await self.session.execute(
            select(ChatSessionShare.session_id, func.count())
            .where(ChatSessionShare.session_id.in_(session_ids))
            .group_by(ChatSessionShare.session_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def get_shared_sessions_with_permissions(self, user_id: int) -> dict[str, str]:
        """Get dict of session_id -> permission for all sessions shared with user."""
        result = await self.session.execute(
            select(ChatSessionShare.session_id, ChatSessionShare.permission).where(
                ChatSessionShare.user_id == user_id
            )
        )
        return {row[0]: row[1] for row in result.all()}
