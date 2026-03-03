"""Database integration — facade re-export for backward compatibility.

All service classes now live in modules/*/service.py.
This file re-exports them under old names and creates module-level singletons
so that existing consumers (routers, orchestrator, bots) keep working.
"""

from modules.admin.service import ResourceShareService as AsyncResourceShareManager
from modules.channels.telegram.service import BotInstanceService as AsyncBotInstanceManager
from modules.channels.telegram.service import TelegramSessionService as AsyncTelegramSessionManager
from modules.channels.whatsapp.service import (
    WhatsAppInstanceService as AsyncWhatsAppInstanceManager,
)
from modules.channels.widget.service import WidgetInstanceService as AsyncWidgetInstanceManager
from modules.chat.service import ChatService as AsyncChatManager
from modules.chat.service import ChatShareService as AsyncChatShareManager
from modules.claude_code.service import ClaudeCodeProjectService as AsyncClaudeCodeProjectManager
from modules.claude_code.service import ClaudeCodeService as AsyncClaudeCodeManager
from modules.core.service import ConfigService as AsyncConfigManager
from modules.core.service import DatabaseService as DatabaseManager
from modules.core.service import RoleService as AsyncRoleManager
from modules.core.service import UserIdentityService as AsyncUserIdentityManager
from modules.core.service import UserService as AsyncUserManager
from modules.core.service import UserSessionService as AsyncUserSessionManager
from modules.core.service import WorkspaceService as AsyncWorkspaceManager
from modules.crm.service import AmoCRMService as AsyncAmoCRMManager
from modules.ecommerce.service import WooCommerceService as AsyncWooCommerceManager
from modules.kanban.service import KanbanProjectService as AsyncKanbanProjectManager
from modules.kanban.service import KanbanService as AsyncKanbanManager
from modules.knowledge.service import FAQService as AsyncFAQManager
from modules.knowledge.service import GitHubRepoProjectService as AsyncGitHubRepoProjectManager
from modules.knowledge.service import KnowledgeCollectionService as AsyncKnowledgeCollectionManager
from modules.knowledge.service import KnowledgeDocService as AsyncKnowledgeDocManager
from modules.llm.service import CloudProviderService as AsyncCloudProviderManager
from modules.monitoring.service import AuditService as AsyncAuditLogger
from modules.monitoring.service import PaymentService as AsyncPaymentManager
from modules.speech.service import PresetService as AsyncPresetManager
from modules.telephony.service import GSMService as AsyncGSMManager


# ---------------------------------------------------------------------------
# Singletons (same names as before)
# ---------------------------------------------------------------------------

db_manager = DatabaseManager()

async_chat_manager = AsyncChatManager()
async_faq_manager = AsyncFAQManager()
async_preset_manager = AsyncPresetManager()
async_config_manager = AsyncConfigManager()
async_telegram_manager = AsyncTelegramSessionManager()
async_audit_logger = AsyncAuditLogger()
async_bot_instance_manager = AsyncBotInstanceManager()
async_widget_instance_manager = AsyncWidgetInstanceManager()
async_whatsapp_instance_manager = AsyncWhatsAppInstanceManager()
async_cloud_provider_manager = AsyncCloudProviderManager()
async_payment_manager = AsyncPaymentManager()
async_amocrm_manager = AsyncAmoCRMManager()
async_woocommerce_manager = AsyncWooCommerceManager()
async_github_repo_project_manager = AsyncGitHubRepoProjectManager()
async_gsm_manager = AsyncGSMManager()
async_user_manager = AsyncUserManager()
async_user_identity_manager = AsyncUserIdentityManager()
async_knowledge_doc_manager = AsyncKnowledgeDocManager()
async_knowledge_collection_manager = AsyncKnowledgeCollectionManager()
async_chat_share_manager = AsyncChatShareManager()
async_resource_share_manager = AsyncResourceShareManager()
async_claude_code_manager = AsyncClaudeCodeManager()
async_claude_code_project_manager = AsyncClaudeCodeProjectManager()
async_kanban_manager = AsyncKanbanManager()
async_kanban_project_manager = AsyncKanbanProjectManager()
async_role_manager = AsyncRoleManager()
async_workspace_manager = AsyncWorkspaceManager()
async_session_manager = AsyncUserSessionManager()

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
