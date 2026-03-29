"""Core domain startup: seed roles/workspace, legacy checks, monitor, shutdown."""

import logging
from pathlib import Path


logger = logging.getLogger(__name__)


async def seed_system_roles() -> None:
    """Seed default RBAC roles if none exist (idempotent)."""
    from db.integration import async_role_manager

    try:
        count = await async_role_manager.count()
        if count > 0:
            logger.info(f"🔐 RBAC: {count} roles already exist, skipping seed")
            return

        ALL_MODULES = [
            "dashboard",
            "chat",
            "llm",
            "speech",
            "faq",
            "wiki",
            "channels",
            "sales",
            "kanban",
            "gsm",
            "system",
            "audit",
            "usage",
            "settings",
            "users",
            "claude_code",
        ]

        SYSTEM_ROLES = [
            {
                "name": "owner",
                "display_name": "Owner",
                "description": "Full system owner with all permissions",
                "permissions": dict.fromkeys(ALL_MODULES, "manage"),
            },
            {
                "name": "admin",
                "display_name": "Administrator",
                "description": "Full administrative access",
                "permissions": dict.fromkeys(ALL_MODULES, "manage"),
            },
            {
                "name": "operator",
                "display_name": "Operator",
                "description": "Day-to-day operations: chat, content, channels",
                "permissions": {
                    **dict.fromkeys(
                        [
                            "chat",
                            "llm",
                            "speech",
                            "faq",
                            "wiki",
                            "channels",
                            "sales",
                            "kanban",
                        ],
                        "edit",
                    ),
                    **dict.fromkeys(["audit", "usage", "dashboard"], "view"),
                },
            },
            {
                "name": "viewer",
                "display_name": "Viewer",
                "description": "Read-only access to key modules",
                "permissions": dict.fromkeys(
                    [
                        "dashboard",
                        "chat",
                        "llm",
                        "faq",
                        "wiki",
                        "kanban",
                        "audit",
                    ],
                    "view",
                ),
            },
        ]

        for role_def in SYSTEM_ROLES:
            await async_role_manager.create_role(
                name=role_def["name"],
                display_name=role_def["display_name"],
                description=role_def["description"],
                is_system=True,
                permissions=role_def["permissions"],
            )

        logger.info(f"🔐 RBAC: seeded {len(SYSTEM_ROLES)} system roles")
    except Exception as e:
        logger.error(f"🔐 RBAC seed failed: {e}")


async def seed_default_workspace() -> None:
    """Seed default workspace and populate workspace_members for all users."""
    from db.integration import async_user_manager, async_workspace_manager

    try:
        ws = await async_workspace_manager.get_default_workspace()
        if ws:
            logger.info("🏢 Workspace: default already exists, checking membership")
        else:
            await async_workspace_manager.create_default(name="Default", slug="default")
            logger.info("🏢 Workspace: created default workspace (id=1)")

        # Populate workspace_members for all users not yet in workspace 1
        _LEGACY_ROLE_MAP = {
            "admin": "admin",
            "user": "operator",
            "web": "operator",
            "guest": "viewer",
        }
        users = await async_user_manager.list_users(include_inactive=True)
        added = 0
        for u in users:
            role_name = _LEGACY_ROLE_MAP.get(u["role"], "viewer")
            await async_workspace_manager.ensure_membership(1, u["id"], role_name)
            added += 1
        if added:
            logger.info(f"🏢 Workspace: ensured {added} users in default workspace")
    except Exception as e:
        logger.error(f"🏢 Workspace seed failed: {e}")


def check_legacy_files() -> None:
    """Warn about deprecated legacy JSON files."""
    legacy_files = [
        ("typical_responses.json", "FAQ"),
        ("custom_presets.json", "TTS presets"),
        ("chat_sessions.json", "chat sessions"),
        ("widget_config.json", "widget config"),
        ("telegram_config.json", "telegram config"),
    ]
    found_legacy = []
    for filename, description in legacy_files:
        if Path(filename).exists():
            found_legacy.append(f"{filename} ({description})")

    if found_legacy:
        logger.warning("=" * 60)
        logger.warning("⚠️  DEPRECATED: Найдены legacy JSON файлы:")
        for f in found_legacy:
            logger.warning(f"    • {f}")
        logger.warning("    Данные теперь хранятся в SQLite (data/secretary.db).")
        logger.warning("    Legacy файлы можно удалить после проверки миграции:")
        logger.warning("    python scripts/migrate_json_to_db.py")
        logger.warning("=" * 60)


async def setup_event_subscriptions(event_bus) -> None:
    """Register event handlers for UserRoleChanged and SessionRevoked."""
    from modules.core.events import SessionRevoked, UserRoleChanged

    async def on_user_role_changed(event: UserRoleChanged) -> None:
        """Invalidate caches and revoke sessions on role change."""
        from modules.core.auth_service import auth_service

        auth_service.invalidate_member_role_cache(event.user_id)
        await auth_service.revoke_all_sessions(event.user_id)
        logger.info(
            "UserRoleChanged handled: user=%d role=%s->%s",
            event.user_id,
            event.old_role,
            event.new_role,
        )

    async def on_session_revoked(event: SessionRevoked) -> None:
        """Revoke all sessions and invalidate caches for a user."""
        from modules.core.auth_service import auth_service

        auth_service.invalidate_member_role_cache(event.user_id)
        await auth_service.revoke_all_sessions(event.user_id)
        logger.info(
            "SessionRevoked handled: user=%d reason=%s",
            event.user_id,
            event.reason,
        )

    event_bus.subscribe(UserRoleChanged, on_user_role_changed)
    event_bus.subscribe(SessionRevoked, on_session_revoked)

    # Config change audit logging
    from modules.core.events import ConfigChanged
    from modules.monitoring.service import audit_service

    async def on_config_changed(event: ConfigChanged) -> None:
        """Log config changes to audit trail."""
        await audit_service.log(
            action="config_changed",
            resource="config",
            resource_id=event.key,
            details={
                "namespace": event.namespace,
                "previous_value": event.previous_value,
                "new_value": event.value,
            },
        )
        logger.info(
            "ConfigChanged handled: key=%s namespace=%s",
            event.key,
            event.namespace,
        )

    event_bus.subscribe(ConfigChanged, on_config_changed)

    # Domain-specific subscriptions
    from modules.channels.startup import setup_channel_event_subscriptions
    from modules.crm.startup import setup_crm_event_subscriptions
    from modules.knowledge.startup import setup_knowledge_event_subscriptions
    from modules.llm.startup import setup_llm_event_subscriptions

    await setup_channel_event_subscriptions(event_bus)
    await setup_crm_event_subscriptions(event_bus)
    await setup_knowledge_event_subscriptions(event_bus)
    await setup_llm_event_subscriptions(event_bus)

    logger.info("Event subscriptions registered")


async def init_internet_monitor(container, deployment_mode: str) -> None:
    """Initialize Internet Monitor + LLM auto-switching (GPU/full mode only)."""
    if deployment_mode == "cloud":
        return

    try:
        from modules.core.internet_monitor import InternetMonitor
        from modules.llm.startup import create_llm_switch_callback

        internet_monitor = InternetMonitor(event_bus=container.event_bus, check_interval=30)
        internet_monitor.set_switch_callback(create_llm_switch_callback(container))
        await internet_monitor.start()
        container.internet_monitor = internet_monitor
        logger.info("✅ InternetMonitor started (auto-switching LLM)")
    except Exception as e:
        logger.warning(f"⚠️ InternetMonitor not available: {e}")


async def graceful_shutdown() -> None:
    """Stop all running bots and bridge."""
    # Stop Telegram bots
    try:
        from multi_bot_manager import multi_bot_manager

        await multi_bot_manager.stop_all()
        logger.info("✅ Telegram bots stopped")
    except Exception as e:
        logger.warning(f"⚠️ Error stopping Telegram bots: {e}")

    # Stop WhatsApp bots
    try:
        from whatsapp_manager import whatsapp_manager

        await whatsapp_manager.stop_all()
        logger.info("✅ WhatsApp bots stopped")
    except Exception as e:
        logger.warning(f"⚠️ Error stopping WhatsApp bots: {e}")

    # Stop Claude bridge
    try:
        from bridge_manager import bridge_manager

        await bridge_manager.stop()
        logger.info("✅ Claude bridge stopped")
    except Exception as e:
        logger.warning(f"⚠️ Error stopping Claude bridge: {e}")
