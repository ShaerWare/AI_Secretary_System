# ruff: noqa: F401
"""Database integration — facade re-export for backward compatibility.

All service classes and singletons now live in modules/*/service.py.
This file re-exports them under old names so that existing consumers
(routers, orchestrator, bots) keep working.
"""

from modules.admin.service import ResourceShareService as AsyncResourceShareManager
from modules.admin.service import resource_share_service as async_resource_share_manager
from modules.channels.telegram.service import BotInstanceService as AsyncBotInstanceManager
from modules.channels.telegram.service import (
    TelegramSessionService as AsyncTelegramSessionManager,
)
from modules.channels.telegram.service import bot_instance_service as async_bot_instance_manager
from modules.channels.telegram.service import telegram_session_service as async_telegram_manager
from modules.channels.whatsapp.service import (
    WhatsAppInstanceService as AsyncWhatsAppInstanceManager,
)
from modules.channels.whatsapp.service import (
    whatsapp_instance_service as async_whatsapp_instance_manager,
)
from modules.channels.widget.service import WidgetInstanceService as AsyncWidgetInstanceManager
from modules.channels.widget.service import (
    widget_instance_service as async_widget_instance_manager,
)
from modules.chat.service import ChatService as AsyncChatManager
from modules.chat.service import ChatShareService as AsyncChatShareManager
from modules.chat.service import chat_service as async_chat_manager
from modules.chat.service import chat_share_service as async_chat_share_manager
from modules.claude_code.service import ClaudeCodeProjectService as AsyncClaudeCodeProjectManager
from modules.claude_code.service import ClaudeCodeService as AsyncClaudeCodeManager
from modules.claude_code.service import (
    claude_code_project_service as async_claude_code_project_manager,
)
from modules.claude_code.service import claude_code_service as async_claude_code_manager
from modules.core.service import ConfigService as AsyncConfigManager
from modules.core.service import DatabaseService as DatabaseManager
from modules.core.service import RoleService as AsyncRoleManager
from modules.core.service import UserIdentityService as AsyncUserIdentityManager
from modules.core.service import UserService as AsyncUserManager
from modules.core.service import UserSessionService as AsyncUserSessionManager
from modules.core.service import WorkspaceService as AsyncWorkspaceManager
from modules.core.service import config_service as async_config_manager
from modules.core.service import database_service as db_manager
from modules.core.service import role_service as async_role_manager
from modules.core.service import user_identity_service as async_user_identity_manager
from modules.core.service import user_service as async_user_manager
from modules.core.service import user_session_service as async_session_manager
from modules.core.service import workspace_service as async_workspace_manager
from modules.crm.service import AmoCRMService as AsyncAmoCRMManager
from modules.crm.service import amocrm_service as async_amocrm_manager
from modules.ecommerce.service import WooCommerceService as AsyncWooCommerceManager
from modules.ecommerce.service import woocommerce_service as async_woocommerce_manager
from modules.kanban.service import KanbanProjectService as AsyncKanbanProjectManager
from modules.kanban.service import KanbanService as AsyncKanbanManager
from modules.kanban.service import kanban_project_service as async_kanban_project_manager
from modules.kanban.service import kanban_service as async_kanban_manager
from modules.knowledge.service import FAQService as AsyncFAQManager
from modules.knowledge.service import GitHubRepoProjectService as AsyncGitHubRepoProjectManager
from modules.knowledge.service import KnowledgeCollectionService as AsyncKnowledgeCollectionManager
from modules.knowledge.service import KnowledgeDocService as AsyncKnowledgeDocManager
from modules.knowledge.service import faq_service as async_faq_manager
from modules.knowledge.service import (
    github_repo_project_service as async_github_repo_project_manager,
)
from modules.knowledge.service import (
    knowledge_collection_service as async_knowledge_collection_manager,
)
from modules.knowledge.service import knowledge_doc_service as async_knowledge_doc_manager
from modules.llm.service import CloudProviderService as AsyncCloudProviderManager
from modules.llm.service import cloud_provider_service as async_cloud_provider_manager
from modules.monitoring.service import AuditService as AsyncAuditLogger
from modules.monitoring.service import PaymentService as AsyncPaymentManager
from modules.monitoring.service import audit_service as async_audit_logger
from modules.monitoring.service import payment_service as async_payment_manager
from modules.speech.service import PresetService as AsyncPresetManager
from modules.speech.service import preset_service as async_preset_manager
from modules.telephony.service import GSMService as AsyncGSMManager
from modules.telephony.service import gsm_service as async_gsm_manager


# ---------------------------------------------------------------------------
# Lifecycle functions
# ---------------------------------------------------------------------------


async def init_database() -> None:
    """Initialize database and Redis."""
    await db_manager.initialize()


async def shutdown_database() -> None:
    """Shutdown database and Redis."""
    await db_manager.shutdown()


async def get_database_status() -> dict:
    """Get database and Redis status."""
    return await db_manager.get_status()
