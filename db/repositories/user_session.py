"""Repository for user session management (token revocation, session tracking)."""

from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from db.models import UserSession
from db.repositories.base import BaseRepository


class UserSessionRepository(BaseRepository[UserSession]):
    """Repository for user session CRUD and revocation."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, UserSession)

    async def create_session(
        self,
        user_id: int,
        jti: str,
        ip_address: Optional[str],
        user_agent: Optional[str],
        expires_at: datetime,
    ) -> dict:
        """Create a new user session record."""
        user_session = UserSession(
            user_id=user_id,
            token_jti=jti,
            ip_address=ip_address,
            user_agent=user_agent[:500] if user_agent and len(user_agent) > 500 else user_agent,
            expires_at=expires_at,
        )
        self.session.add(user_session)
        await self.session.commit()
        await self.session.refresh(user_session)
        return user_session.to_dict()

    async def get_by_jti(self, jti: str) -> Optional[UserSession]:
        """Get session by JTI, eagerly loading user for is_active check."""
        result = await self.session.execute(
            select(UserSession)
            .options(joinedload(UserSession.user))
            .where(UserSession.token_jti == jti)
        )
        return result.scalar_one_or_none()

    async def get_active_for_user(self, user_id: int) -> List[dict]:
        """Get all active (non-revoked, non-expired) sessions for a user."""
        now = datetime.utcnow()
        result = await self.session.execute(
            select(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
            .order_by(UserSession.created_at.desc())
        )
        sessions = result.scalars().all()
        return [s.to_dict() for s in sessions]

    async def revoke_by_jti(self, jti: str) -> bool:
        """Revoke a session by JTI. Returns True if found and revoked."""
        result = await self.session.execute(
            update(UserSession)
            .where(UserSession.token_jti == jti, UserSession.revoked_at.is_(None))
            .values(revoked_at=datetime.utcnow())
        )
        await self.session.commit()
        return result.rowcount > 0

    async def revoke_all_for_user(self, user_id: int) -> int:
        """Revoke all active sessions for a user. Returns count revoked."""
        result = await self.session.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=datetime.utcnow())
        )
        await self.session.commit()
        return result.rowcount

    async def cleanup_expired(self, days: int = 7) -> int:
        """Delete sessions that expired more than `days` ago."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = await self.session.execute(
            delete(UserSession).where(UserSession.expires_at < cutoff)
        )
        await self.session.commit()
        return result.rowcount
