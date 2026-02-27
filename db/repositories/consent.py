"""User consent repository for GDPR/legal compliance."""

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import CONSENT_TYPES, UserConsent
from db.repositories.base import BaseRepository


class ConsentRepository(BaseRepository[UserConsent]):
    """Repository for user consent management."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, UserConsent)

    async def get_user_consents(self, user_id: str) -> List[dict]:
        """Get all consents for a user."""
        result = await self.session.execute(
            select(UserConsent).where(UserConsent.user_id == user_id)
        )
        return [c.to_dict() for c in result.scalars().all()]

    async def get_consent(self, user_id: str, consent_type: str) -> Optional[dict]:
        """Get a specific consent for a user."""
        result = await self.session.execute(
            select(UserConsent).where(
                and_(
                    UserConsent.user_id == user_id,
                    UserConsent.consent_type == consent_type,
                )
            )
        )
        consent = result.scalars().first()
        return consent.to_dict() if consent else None

    async def grant_consent(
        self,
        user_id: str,
        user_type: str,
        consent_type: str,
        consent_version: str = "1.0",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        """Grant a consent (create or update)."""
        # Check if consent exists
        result = await self.session.execute(
            select(UserConsent).where(
                and_(
                    UserConsent.user_id == user_id,
                    UserConsent.consent_type == consent_type,
                )
            )
        )
        consent = result.scalars().first()

        if consent:
            # Update existing consent
            consent.granted = True
            consent.granted_at = datetime.utcnow()
            consent.revoked_at = None
            consent.consent_version = consent_version
            consent.ip_address = ip_address
            consent.user_agent = user_agent
        else:
            # Create new consent
            consent = UserConsent(
                user_id=user_id,
                user_type=user_type,
                consent_type=consent_type,
                consent_version=consent_version,
                granted=True,
                granted_at=datetime.utcnow(),
                ip_address=ip_address,
                user_agent=user_agent,
            )
            self.session.add(consent)

        await self.session.flush()
        await self.session.commit()
        return consent.to_dict()

    async def revoke_consent(self, user_id: str, consent_type: str) -> Optional[dict]:
        """Revoke a consent."""
        result = await self.session.execute(
            select(UserConsent).where(
                and_(
                    UserConsent.user_id == user_id,
                    UserConsent.consent_type == consent_type,
                )
            )
        )
        consent = result.scalars().first()

        if consent:
            consent.granted = False
            consent.revoked_at = datetime.utcnow()
            await self.session.commit()
            return consent.to_dict()
        return None

    async def check_required_consents(self, user_id: str) -> Dict:
        """Check if user has granted all required consents."""
        user_consents = await self.get_user_consents(user_id)
        granted_types = {c["consent_type"] for c in user_consents if c["granted"]}

        missing = []
        for consent_type, info in CONSENT_TYPES.items():
            if info["required"] and consent_type not in granted_types:
                missing.append(consent_type)

        return {
            "all_required_granted": len(missing) == 0,
            "missing_required": missing,
            "granted_consents": list(granted_types),
        }

    async def grant_all_required(
        self,
        user_id: str,
        user_type: str,
        consent_version: str = "1.0",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> List[dict]:
        """Grant all required consents at once."""
        granted = []
        for consent_type, info in CONSENT_TYPES.items():
            if info["required"]:
                consent = await self.grant_consent(
                    user_id=user_id,
                    user_type=user_type,
                    consent_type=consent_type,
                    consent_version=consent_version,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                granted.append(consent)
        return granted

    async def delete_user_data(self, user_id: str) -> Dict:
        """Delete all consent records for a user (GDPR right to erasure)."""
        result = await self.session.execute(
            select(UserConsent).where(UserConsent.user_id == user_id)
        )
        consents = result.scalars().all()
        count = len(consents)

        for consent in consents:
            await self.session.delete(consent)

        await self.session.commit()
        return {"deleted": count, "user_id": user_id}

    async def get_consent_stats(self) -> Dict:
        """Get consent statistics."""
        result = await self.session.execute(select(UserConsent))
        all_consents = result.scalars().all()

        by_type: Dict[str, Dict[str, int]] = {}
        by_user_type: Dict[str, int] = {}

        for consent in all_consents:
            # By consent type
            if consent.consent_type not in by_type:
                by_type[consent.consent_type] = {"granted": 0, "revoked": 0}
            if consent.granted:
                by_type[consent.consent_type]["granted"] += 1
            else:
                by_type[consent.consent_type]["revoked"] += 1

            # By user type
            if consent.user_type not in by_user_type:
                by_user_type[consent.user_type] = 0
            by_user_type[consent.user_type] += 1

        return {
            "total_users": len({c.user_id for c in all_consents}),
            "total_consents": len(all_consents),
            "by_type": by_type,
            "by_user_type": by_user_type,
        }
