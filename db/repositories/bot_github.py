"""
Bot GitHub config repository for managing GitHub webhook and PR comment settings.
"""

import logging
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BotGithubConfig
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


class BotGithubRepository(BaseRepository[BotGithubConfig]):
    """Repository for bot GitHub configurations."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, BotGithubConfig)

    async def get_config(self, bot_id: str) -> Optional[dict]:
        """Get GitHub config for a bot.

        Args:
            bot_id: Bot instance ID.

        Returns:
            Config dict or None if not configured.
        """
        result = await self.session.execute(
            select(BotGithubConfig).where(BotGithubConfig.bot_id == bot_id)
        )
        config = result.scalar_one_or_none()
        return config.to_dict() if config else None

    async def save_config(self, bot_id: str, **kwargs: Any) -> dict:
        """Create or update GitHub config for a bot.

        If config already exists for this bot_id, updates it.
        Otherwise creates a new one.

        Args:
            bot_id: Bot instance ID.
            **kwargs: Config fields (repo_owner, repo_name, github_token, etc.).

        Returns:
            Saved config dict.
        """
        result = await self.session.execute(
            select(BotGithubConfig).where(BotGithubConfig.bot_id == bot_id)
        )
        config = result.scalar_one_or_none()

        if config:
            # Update existing config
            events = kwargs.pop("events", None)
            if events is not None:
                config.set_events(events)
            for k, v in kwargs.items():
                if hasattr(config, k):
                    setattr(config, k, v)
            config.updated = datetime.utcnow()
            await self.session.flush()
            logger.info(f"Updated GitHub config: bot_id={bot_id}")
            return config.to_dict()

        # Create new config
        events = kwargs.pop("events", None)
        config = BotGithubConfig(
            bot_id=bot_id,
            created=datetime.utcnow(),
            updated=datetime.utcnow(),
            **kwargs,
        )
        if events is not None:
            config.set_events(events)
        self.session.add(config)
        await self.session.flush()
        logger.info(f"Created GitHub config: bot_id={bot_id}")
        return config.to_dict()

    async def delete_config(self, bot_id: str) -> bool:
        """Delete GitHub config for a bot.

        Args:
            bot_id: Bot instance ID.

        Returns:
            True if deleted, False if not found.
        """
        result = await self.session.execute(
            select(BotGithubConfig).where(BotGithubConfig.bot_id == bot_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            return False
        await self.session.delete(config)
        await self.session.flush()
        logger.info(f"Deleted GitHub config: bot_id={bot_id}")
        return True

    async def get_all_configs(self) -> List[dict]:
        """Get all GitHub configs across all bots (for webhook routing).

        Returns:
            List of all config dicts.
        """
        result = await self.session.execute(
            select(BotGithubConfig).order_by(BotGithubConfig.bot_id)
        )
        return [c.to_dict() for c in result.scalars().all()]
