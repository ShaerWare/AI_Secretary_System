"""CRM services."""

import logging
from typing import Any, Dict, List, Optional

from db.database import AsyncSessionLocal
from db.repositories import AmoCRMConfigRepository, AmoCRMSyncLogRepository


logger = logging.getLogger(__name__)


class AmoCRMService:
    """Async wrapper for amoCRM config and sync log repositories."""

    async def get_config(self, workspace_id: Optional[int] = None) -> Optional[dict]:
        """Get amoCRM config (secrets masked)."""
        async with AsyncSessionLocal() as session:
            repo = AmoCRMConfigRepository(session)
            return await repo.get_config(workspace_id=workspace_id)

    async def get_config_with_secrets(
        self, workspace_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Get raw config model for internal use (tokens, secrets)."""
        async with AsyncSessionLocal() as session:
            repo = AmoCRMConfigRepository(session)
            model = await repo.get_config_with_secrets(workspace_id=workspace_id)
            if not model:
                return None
            result = model.to_dict(include_secrets=True)
            result["access_token"] = model.access_token
            result["refresh_token"] = model.refresh_token
            result["token_expires_at"] = (
                model.token_expires_at.isoformat() if model.token_expires_at else None
            )
            return result

    async def save_config(self, workspace_id: Optional[int] = None, **kwargs: Any) -> dict:
        """Create or update amoCRM config."""
        async with AsyncSessionLocal() as session:
            repo = AmoCRMConfigRepository(session)
            result = await repo.save_config(workspace_id=workspace_id, **kwargs)
            await session.commit()
            return result

    async def clear_tokens(self, workspace_id: Optional[int] = None) -> dict:
        """Clear OAuth tokens (disconnect)."""
        async with AsyncSessionLocal() as session:
            repo = AmoCRMConfigRepository(session)
            result = await repo.clear_tokens(workspace_id=workspace_id)
            await session.commit()
            return result

    async def log_sync(self, **kwargs: Any) -> dict:
        """Log a sync event."""
        async with AsyncSessionLocal() as session:
            repo = AmoCRMSyncLogRepository(session)
            result = await repo.log_sync(**kwargs)
            await session.commit()
            return result

    async def get_sync_logs(self, limit: int = 50) -> List[dict]:
        """Get recent sync log entries."""
        async with AsyncSessionLocal() as session:
            repo = AmoCRMSyncLogRepository(session)
            return await repo.get_recent(limit)
