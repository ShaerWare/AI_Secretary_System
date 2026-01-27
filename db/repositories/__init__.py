"""
Repository pattern implementations for database access.

Each repository handles CRUD operations for a specific domain entity,
with optional Redis caching for frequently accessed data.
"""

from db.repositories.audit import AuditRepository
from db.repositories.base import BaseRepository
from db.repositories.bot_instance import BotInstanceRepository
from db.repositories.chat import ChatRepository
from db.repositories.cloud_provider import CloudProviderRepository
from db.repositories.config import ConfigRepository
from db.repositories.faq import FAQRepository
from db.repositories.preset import PresetRepository
from db.repositories.telegram import TelegramRepository
from db.repositories.widget_instance import WidgetInstanceRepository


__all__ = [
    "AuditRepository",
    "BaseRepository",
    "BotInstanceRepository",
    "ChatRepository",
    "CloudProviderRepository",
    "ConfigRepository",
    "FAQRepository",
    "PresetRepository",
    "TelegramRepository",
    "WidgetInstanceRepository",
]
