"""
Repository pattern implementations for database access.

Each repository handles CRUD operations for a specific domain entity,
with optional Redis caching for frequently accessed data.
"""

from db.repositories.amocrm import AmoCRMConfigRepository, AmoCRMSyncLogRepository
from db.repositories.audit import AuditRepository
from db.repositories.base import BaseRepository
from db.repositories.bot_ab_test import BotAbTestRepository
from db.repositories.bot_agent_prompt import BotAgentPromptRepository
from db.repositories.bot_discovery import BotDiscoveryRepository
from db.repositories.bot_event import BotEventRepository
from db.repositories.bot_followup import BotFollowupQueueRepository, BotFollowupRuleRepository
from db.repositories.bot_github import BotGithubRepository
from db.repositories.bot_hardware import BotHardwareRepository
from db.repositories.bot_instance import BotInstanceRepository
from db.repositories.bot_quiz import BotQuizRepository
from db.repositories.bot_segment import BotSegmentRepository
from db.repositories.bot_subscriber import BotSubscriberRepository
from db.repositories.bot_testimonial import BotTestimonialRepository
from db.repositories.bot_user_profile import BotUserProfileRepository
from db.repositories.chat import ChatRepository
from db.repositories.chat_share import ChatShareRepository
from db.repositories.cloud_provider import CloudProviderRepository
from db.repositories.config import ConfigRepository
from db.repositories.consent import ConsentRepository
from db.repositories.faq import FAQRepository
from db.repositories.gsm import GSMCallLogRepository, GSMSMSLogRepository
from db.repositories.knowledge_collection import KnowledgeCollectionRepository
from db.repositories.knowledge_document import KnowledgeDocumentRepository
from db.repositories.payment import PaymentRepository
from db.repositories.preset import PresetRepository
from db.repositories.telegram import TelegramRepository
from db.repositories.usage import UsageLimitsRepository, UsageRepository
from db.repositories.user import UserRepository
from db.repositories.whatsapp_instance import WhatsAppInstanceRepository
from db.repositories.widget_instance import WidgetInstanceRepository


__all__ = [
    "AmoCRMConfigRepository",
    "AmoCRMSyncLogRepository",
    "AuditRepository",
    "BaseRepository",
    "BotAbTestRepository",
    "BotAgentPromptRepository",
    "BotDiscoveryRepository",
    "BotEventRepository",
    "BotFollowupQueueRepository",
    "BotFollowupRuleRepository",
    "BotGithubRepository",
    "BotHardwareRepository",
    "BotInstanceRepository",
    "BotQuizRepository",
    "BotSegmentRepository",
    "BotSubscriberRepository",
    "BotTestimonialRepository",
    "BotUserProfileRepository",
    "ChatRepository",
    "ChatShareRepository",
    "CloudProviderRepository",
    "ConfigRepository",
    "ConsentRepository",
    "FAQRepository",
    "GSMCallLogRepository",
    "GSMSMSLogRepository",
    "KnowledgeCollectionRepository",
    "KnowledgeDocumentRepository",
    "PaymentRepository",
    "PresetRepository",
    "TelegramRepository",
    "UsageLimitsRepository",
    "UserRepository",
    "UsageRepository",
    "WhatsAppInstanceRepository",
    "WidgetInstanceRepository",
]
