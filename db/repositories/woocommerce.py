"""WooCommerce config repository."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import WooCommerceConfig
from db.repositories.base import BaseRepository


class WooCommerceConfigRepository(BaseRepository[WooCommerceConfig]):
    """Repository for WooCommerce singleton config."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, WooCommerceConfig)

    async def get_config(self) -> Optional[dict]:
        """Get the singleton config row (id=1), masked secrets."""
        config = await self.session.get(WooCommerceConfig, 1)
        return config.to_dict() if config else None

    async def get_config_with_secrets(self) -> Optional[WooCommerceConfig]:
        """Get raw model for internal use (credentials)."""
        return await self.session.get(WooCommerceConfig, 1)

    async def save_config(self, **kwargs: Any) -> dict:
        """Create or update the singleton config."""
        config = await self.session.get(WooCommerceConfig, 1)
        if not config:
            config = WooCommerceConfig(id=1)
            self.session.add(config)

        simple_fields = [
            "store_url",
            "consumer_key",
            "consumer_secret",
            "is_connected",
            "sync_enabled",
            "last_sync_at",
            "products_count",
            "categories_count",
            "orders_count",
        ]
        for field in simple_fields:
            if field in kwargs:
                setattr(config, field, kwargs[field])

        config.updated = datetime.utcnow()
        await self.session.flush()
        return config.to_dict()

    async def clear_credentials(self) -> dict:
        """Clear store credentials (disconnect)."""
        config = await self.session.get(WooCommerceConfig, 1)
        if not config:
            return {}
        config.consumer_key = ""
        config.consumer_secret = ""
        config.is_connected = False
        config.updated = datetime.utcnow()
        await self.session.flush()
        return config.to_dict()
