"""Kanban domain background tasks: periodic GitHub issue sync."""

import logging


logger = logging.getLogger(__name__)


async def sync_kanban_issues() -> None:
    """Sync GitHub issues to Kanban projects that have sync enabled."""
    from app.services.github_kanban_sync import sync_all_issues
    from db.integration import async_kanban_project_manager

    projects = await async_kanban_project_manager.get_all_projects()
    for proj in projects:
        if proj.get("sync_enabled") and proj.get("has_token", False):
            try:
                result = await sync_all_issues(proj["id"])
                if result["created"] > 0:
                    logger.info(
                        f"Kanban sync {proj['name']}: "
                        f"+{result['created']} new, {result['total']} total"
                    )
            except Exception as e:
                logger.warning(f"Kanban sync failed for {proj['name']}: {e}")
