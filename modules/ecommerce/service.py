"""Ecommerce services."""

import logging
from typing import Any, Dict, Optional

from db.database import AsyncSessionLocal
from db.repositories import WooCommerceConfigRepository


logger = logging.getLogger(__name__)


class WooCommerceService:
    """Async wrapper for WooCommerce config repository."""

    async def get_config(self) -> Optional[dict]:
        """Get WooCommerce config (secrets masked)."""
        async with AsyncSessionLocal() as session:
            repo = WooCommerceConfigRepository(session)
            return await repo.get_config()

    async def get_config_with_secrets(self) -> Optional[Dict[str, Any]]:
        """Get raw config for internal use (credentials)."""
        async with AsyncSessionLocal() as session:
            repo = WooCommerceConfigRepository(session)
            model = await repo.get_config_with_secrets()
            if not model:
                return None
            return model.to_dict(include_secrets=True)

    async def save_config(self, **kwargs: Any) -> dict:
        """Create or update WooCommerce config."""
        async with AsyncSessionLocal() as session:
            repo = WooCommerceConfigRepository(session)
            result = await repo.save_config(**kwargs)
            await session.commit()
            return result

    async def clear_credentials(self) -> dict:
        """Clear store credentials (disconnect)."""
        async with AsyncSessionLocal() as session:
            repo = WooCommerceConfigRepository(session)
            result = await repo.clear_credentials()
            await session.commit()
            return result
