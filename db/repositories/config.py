"""
Config repository for system configuration key-value store.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import SystemConfig
from db.redis_client import (
    cache_config,
    get_cached_config,
    invalidate_config_cache,
)
from db.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


# Default configurations
DEFAULT_CONFIGS = {
    "telegram": {
        "enabled": False,
        "bot_token": "",
        "api_url": "http://localhost:8002",
        "allowed_users": [],
        "admin_users": [],
        "welcome_message": "Здравствуйте! Я AI-ассистент компании Шаервэй. Чем могу помочь?",
        "unauthorized_message": "Извините, у вас нет доступа к этому боту.",
        "error_message": "Произошла ошибка. Попробуйте позже.",
        "typing_enabled": True,
        "max_message_length": 4096,
    },
    "widget": {
        "enabled": False,
        "title": "AI Ассистент",
        "welcome_message": "Здравствуйте! Чем могу помочь?",
        "placeholder": "Введите сообщение...",
        "primary_color": "#4f46e5",
        "position": "bottom-right",
        "api_url": "",
        "tunnel_url": "",
    },
    "llm": {
        "backend": "vllm",
        "persona": "gulya",
        "temperature": 0.7,
        "max_tokens": 512,
        "repetition_penalty": 1.1,
    },
    "tts": {
        "engine": "xtts",
        "voice": "gulya",
        "preset": "neutral",
    },
}


class ConfigRepository(BaseRepository[SystemConfig]):
    """Repository for system configuration."""

    CACHE_TTL = 300  # 5 minutes

    def __init__(self, session: AsyncSession):
        super().__init__(session, SystemConfig)

    async def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key.
        Returns default if not found.
        Uses Redis cache.
        """
        # Try cache first
        cached = await get_cached_config(key)
        if cached is not None:
            return cached

        # Fetch from database
        config = await self.session.get(SystemConfig, key)
        if config:
            value = config.get_value()
            await cache_config(key, value, self.CACHE_TTL)
            return value

        # Return default from DEFAULT_CONFIGS if available
        if default is None and key in DEFAULT_CONFIGS:
            return DEFAULT_CONFIGS[key].copy()

        return default

    async def set_config(self, key: str, value: Any) -> bool:
        """
        Set configuration value.
        Creates new entry if doesn't exist, updates otherwise.
        """
        config = await self.session.get(SystemConfig, key)

        if config:
            config.value = json.dumps(value, ensure_ascii=False)
            config.updated = datetime.utcnow()
        else:
            config = SystemConfig(
                key=key,
                value=json.dumps(value, ensure_ascii=False),
                updated=datetime.utcnow(),
            )
            self.session.add(config)

        await self.session.commit()
        await invalidate_config_cache(key)

        return True

    async def delete_config(self, key: str) -> bool:
        """Delete configuration by key."""
        result = await self.session.execute(delete(SystemConfig).where(SystemConfig.key == key))
        await self.session.commit()
        await invalidate_config_cache(key)
        return result.rowcount > 0

    async def get_all_configs(self) -> Dict[str, Any]:
        """Get all configuration as dict."""
        result = await self.session.execute(select(SystemConfig))
        configs = result.scalars().all()

        return {c.key: c.get_value() for c in configs}

    async def update_config(self, key: str, updates: Dict[str, Any]) -> Any:
        """
        Merge updates into existing config.
        Useful for partial updates.
        """
        current = await self.get_config(key, {})

        if isinstance(current, dict):
            current.update(updates)
        else:
            current = updates

        await self.set_config(key, current)
        return current

    # ============== Telegram Config ==============

    async def get_telegram_config(self) -> dict:
        """Get Telegram bot configuration."""
        return await self.get_config("telegram", DEFAULT_CONFIGS["telegram"])

    async def set_telegram_config(self, config: dict) -> bool:
        """Set Telegram bot configuration."""
        current = await self.get_telegram_config()
        current.update(config)
        return await self.set_config("telegram", current)

    # ============== Widget Config ==============

    async def get_widget_config(self) -> dict:
        """Get widget configuration."""
        return await self.get_config("widget", DEFAULT_CONFIGS["widget"])

    async def set_widget_config(self, config: dict) -> bool:
        """Set widget configuration."""
        current = await self.get_widget_config()
        current.update(config)
        return await self.set_config("widget", current)

    # ============== LLM Config ==============

    async def get_llm_config(self) -> dict:
        """Get LLM configuration."""
        return await self.get_config("llm", DEFAULT_CONFIGS["llm"])

    async def set_llm_config(self, config: dict) -> bool:
        """Set LLM configuration."""
        current = await self.get_llm_config()
        current.update(config)
        return await self.set_config("llm", current)

    # ============== TTS Config ==============

    async def get_tts_config(self) -> dict:
        """Get TTS configuration."""
        return await self.get_config("tts", DEFAULT_CONFIGS["tts"])

    async def set_tts_config(self, config: dict) -> bool:
        """Set TTS configuration."""
        current = await self.get_tts_config()
        current.update(config)
        return await self.set_config("tts", current)

    # ============== Import/Export ==============

    async def import_from_json_file(
        self,
        key: str,
        file_content: str,
    ) -> bool:
        """Import config from JSON file content."""
        try:
            data = json.loads(file_content)
            return await self.set_config(key, data)
        except json.JSONDecodeError:
            return False

    async def export_to_json(self, key: str) -> Optional[str]:
        """Export config to JSON string."""
        value = await self.get_config(key)
        if value is not None:
            return json.dumps(value, indent=2, ensure_ascii=False)
        return None
