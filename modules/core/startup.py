"""Core domain startup: seed system roles and default workspace."""

import logging

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
