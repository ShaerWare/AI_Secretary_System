"""Repository for user identity CRUD (Telegram, WhatsApp, Widget contacts)."""

import json
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User, UserIdentity
from db.repositories.base import BaseRepository


class UserIdentityRepository(BaseRepository[UserIdentity]):
    """Repository for external user identities."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, UserIdentity)

    async def get_by_provider_uid(self, provider: str, provider_uid: str) -> Optional[UserIdentity]:
        """Look up an identity by provider + uid."""
        result = await self.session.execute(
            select(UserIdentity).where(
                UserIdentity.provider == provider,
                UserIdentity.provider_uid == provider_uid,
            )
        )
        return result.scalar_one_or_none()

    async def find_or_create(
        self,
        provider: str,
        provider_uid: str,
        display_name: Optional[str] = None,
        metadata_dict: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Find existing identity or create a new contact user + identity.

        Returns the linked user as a dict.
        """
        identity = await self.get_by_provider_uid(provider, provider_uid)

        if identity:
            # Update display_name / metadata if provided
            changed = False
            if display_name and display_name != identity.display_name:
                identity.display_name = display_name
                changed = True
            if metadata_dict:
                identity.metadata_json = json.dumps(metadata_dict, ensure_ascii=False)
                changed = True
            identity.last_seen = datetime.utcnow()
            if changed:
                await self.session.commit()
            else:
                await self.session.commit()

            user = await self.session.get(User, identity.user_id)
            return user.to_dict() if user else {}

        # Create contact user (no credentials)
        user = User(
            username=None,
            password_hash=None,
            role="contact",
            display_name=display_name,
            is_active=True,
        )
        self.session.add(user)
        await self.session.flush()  # get user.id

        identity = UserIdentity(
            user_id=user.id,
            provider=provider,
            provider_uid=provider_uid,
            display_name=display_name,
            metadata_json=json.dumps(metadata_dict, ensure_ascii=False) if metadata_dict else None,
            last_seen=datetime.utcnow(),
        )
        self.session.add(identity)
        await self.session.commit()
        return user.to_dict()

    async def get_identities_for_user(self, user_id: int) -> List[dict]:
        """Get all identities for a user."""
        result = await self.session.execute(
            select(UserIdentity).where(UserIdentity.user_id == user_id)
        )
        return [i.to_dict() for i in result.scalars().all()]

    async def link_identity(
        self,
        user_id: int,
        provider: str,
        provider_uid: str,
        display_name: Optional[str] = None,
        metadata_dict: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Link an external identity to an existing user."""
        identity = UserIdentity(
            user_id=user_id,
            provider=provider,
            provider_uid=provider_uid,
            display_name=display_name,
            metadata_json=json.dumps(metadata_dict, ensure_ascii=False) if metadata_dict else None,
            last_seen=datetime.utcnow(),
        )
        self.session.add(identity)
        await self.session.flush()
        await self.session.commit()
        return identity.to_dict()

    async def update_last_seen(self, provider: str, provider_uid: str) -> bool:
        """Touch the last_seen timestamp for an identity."""
        identity = await self.get_by_provider_uid(provider, provider_uid)
        if not identity:
            return False
        identity.last_seen = datetime.utcnow()
        await self.session.commit()
        return True
