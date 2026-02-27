"""
Bot A/B test repository for managing A/B test definitions and variant assignment.
"""

import hashlib
import logging
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BotAbTest
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


class BotAbTestRepository(BaseRepository[BotAbTest]):
    """Repository for bot A/B tests."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, BotAbTest)

    async def list_by_bot(self, bot_id: str) -> List[dict]:
        """List all A/B tests for a bot."""
        result = await self.session.execute(
            select(BotAbTest).where(BotAbTest.bot_id == bot_id).order_by(BotAbTest.created.desc())
        )
        return [t.to_dict() for t in result.scalars().all()]

    async def get_active(self, bot_id: str, test_key: str) -> Optional[BotAbTest]:
        """Get an active A/B test by bot_id and test_key.

        Args:
            bot_id: Bot instance ID.
            test_key: Test key (e.g., "welcome_message", "urgency_slots").

        Returns:
            Active BotAbTest or None.
        """
        result = await self.session.execute(
            select(BotAbTest).where(
                BotAbTest.bot_id == bot_id,
                BotAbTest.test_key == test_key,
                BotAbTest.active == True,
            )
        )
        return result.scalar_one_or_none()

    async def assign_variant(self, test_key: str, user_id: int) -> Optional[str]:
        """Assign a deterministic variant to a user based on user_id hash.

        The variant is deterministic: same user_id always gets the same variant
        for the same test_key. This uses a hash-based assignment.

        Args:
            test_key: Test key to look up variants.
            user_id: User ID to assign a variant to.

        Returns:
            Variant key (e.g., "A" or "B"), or None if test not found or inactive.
        """
        # Find any active test with this key (across all bots)
        result = await self.session.execute(
            select(BotAbTest).where(
                BotAbTest.test_key == test_key,
                BotAbTest.active == True,
            )
        )
        test = result.scalar_one_or_none()
        if not test:
            return None

        variants = test.get_variants()
        if not variants:
            return None

        variant_keys = sorted(variants.keys())
        # Deterministic hash: same user_id + test_key = same variant
        hash_input = f"{test_key}:{user_id}"
        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
        variant_index = hash_value % len(variant_keys)

        assigned: str = variant_keys[variant_index]
        logger.debug(f"Assigned variant '{assigned}' for test_key={test_key}, user_id={user_id}")
        return assigned

    async def create_test(self, bot_id: str, **kwargs: Any) -> dict:
        """Create a new A/B test."""
        variants = kwargs.pop("variants", {})
        test = BotAbTest(bot_id=bot_id, **kwargs)
        if variants:
            test.set_variants(variants)
        self.session.add(test)
        await self.session.flush()
        await self.session.commit()
        logger.info(f"Created A/B test: bot_id={bot_id}, key={kwargs.get('test_key')}")
        return test.to_dict()

    async def update_test(self, test_id: int, **kwargs: Any) -> Optional[dict]:
        """Update an existing A/B test."""
        test = await self.session.get(BotAbTest, test_id)
        if not test:
            return None
        variants = kwargs.pop("variants", None)
        if variants is not None:
            test.set_variants(variants)
        for k, v in kwargs.items():
            if hasattr(test, k):
                setattr(test, k, v)
        test.updated = datetime.utcnow()
        await self.session.commit()
        logger.info(f"Updated A/B test: id={test_id}")
        return test.to_dict()

    async def delete_test(self, test_id: int) -> bool:
        """Delete an A/B test by ID."""
        return await self.delete_by_id(test_id)
