"""SQLAlchemy ORM models — facade re-export for backward compatibility.

All models live in modules/{domain}/models.py.
This file re-exports everything so existing imports continue to work.
"""

# Re-export Base
from db.database import Base

# Domain models
from modules.admin.models import CONSENT_TYPES, UserConsent
from modules.channels.mobile.models import MobileAppInstance
from modules.channels.telegram.models import (
    DEFAULT_ACTION_BUTTONS,
    DEFAULT_AGENT_PROMPTS,
    DEFAULT_FOLLOWUP_RULES,
    DEFAULT_HARDWARE_SPECS,
    DEFAULT_QUIZ_QUESTIONS,
    DEFAULT_SEGMENTS,
    DEFAULT_TESTIMONIALS,
    BotAbTest,
    BotAgentPrompt,
    BotDiscoveryResponse,
    BotEvent,
    BotFollowupQueue,
    BotFollowupRule,
    BotGithubConfig,
    BotHardwareSpec,
    BotInstance,
    BotQuizQuestion,
    BotSegment,
    BotSubscriber,
    BotTestimonial,
    BotUserProfile,
    TelegramSession,
)
from modules.channels.whatsapp.models import WhatsAppInstance
from modules.channels.widget.models import WidgetInstance
from modules.chat.models import (
    ChatMessage,
    ChatSession,
    ChatSessionPrompt,
    ChatSessionShare,
    ResourceShare,
)
from modules.claude_code.models import ClaudeCodeProject, ClaudeCodeSession
from modules.core.models import (
    Role,
    RolePermission,
    SystemConfig,
    User,
    UserIdentity,
    UserSession,
    Workspace,
    WorkspaceInvite,
    WorkspaceMember,
)
from modules.crm.models import AmoCRMConfig, AmoCRMSyncLog
from modules.ecommerce.models import WooCommerceConfig
from modules.kanban.models import (
    KanbanChecklistItem,
    KanbanProject,
    KanbanTask,
    KanbanTaskDependency,
    KanbanTaskStatus,
)
from modules.knowledge.models import (
    GITHUB_DEFAULT_EXCLUDE,
    GITHUB_DEFAULT_INCLUDE,
    FAQEntry,
    GitHubRepoProject,
    KnowledgeCollection,
    KnowledgeDocument,
    RSSFeed,
    RSSFeedItem,
)
from modules.llm.models import (
    DEFAULT_LLM_PRESETS,
    PROVIDER_TYPES,
    CloudLLMProvider,
    LLMPreset,
)
from modules.monitoring.models import AuditLog, UsageLimits, UsageLog
from modules.sales.models import PaymentLog
from modules.speech.models import TTSPreset
from modules.telephony.models import GSMCallLog, GSMSMSLog


__all__ = [
    "Base",
    # core
    "User",
    "UserIdentity",
    "UserSession",
    "Role",
    "RolePermission",
    "Workspace",
    "WorkspaceMember",
    "WorkspaceInvite",
    "SystemConfig",
    # chat
    "ChatSession",
    "ChatMessage",
    "ChatSessionPrompt",
    "ChatSessionShare",
    "ResourceShare",
    # channels
    "BotInstance",
    "TelegramSession",
    "MobileAppInstance",
    "WidgetInstance",
    "WhatsAppInstance",
    # telegram sales
    "BotAgentPrompt",
    "BotQuizQuestion",
    "BotSegment",
    "BotUserProfile",
    "BotFollowupRule",
    "BotFollowupQueue",
    "BotEvent",
    "BotTestimonial",
    "BotHardwareSpec",
    "BotAbTest",
    "BotDiscoveryResponse",
    "BotSubscriber",
    "BotGithubConfig",
    # llm
    "CloudLLMProvider",
    "LLMPreset",
    "PROVIDER_TYPES",
    "DEFAULT_LLM_PRESETS",
    # knowledge
    "FAQEntry",
    "KnowledgeCollection",
    "KnowledgeDocument",
    "GitHubRepoProject",
    "RSSFeed",
    "RSSFeedItem",
    "GITHUB_DEFAULT_INCLUDE",
    "GITHUB_DEFAULT_EXCLUDE",
    # speech
    "TTSPreset",
    # monitoring
    "AuditLog",
    "UsageLog",
    "UsageLimits",
    # sales
    "PaymentLog",
    # admin
    "UserConsent",
    "CONSENT_TYPES",
    # crm
    "AmoCRMConfig",
    "AmoCRMSyncLog",
    # ecommerce
    "WooCommerceConfig",
    # telephony
    "GSMCallLog",
    "GSMSMSLog",
    # kanban
    "KanbanProject",
    "KanbanTask",
    "KanbanTaskDependency",
    "KanbanChecklistItem",
    "KanbanTaskStatus",
    # claude_code
    "ClaudeCodeSession",
    "ClaudeCodeProject",
    # telegram constants
    "DEFAULT_ACTION_BUTTONS",
    "DEFAULT_AGENT_PROMPTS",
    "DEFAULT_QUIZ_QUESTIONS",
    "DEFAULT_SEGMENTS",
    "DEFAULT_HARDWARE_SPECS",
    "DEFAULT_FOLLOWUP_RULES",
    "DEFAULT_TESTIMONIALS",
]
