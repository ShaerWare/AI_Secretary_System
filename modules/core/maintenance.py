"""Core maintenance background tasks: session cleanup, periodic VACUUM."""

import logging


logger = logging.getLogger(__name__)


async def cleanup_expired_sessions():
    """Delete sessions older than 7 days."""
    from db.integration import async_session_manager

    count = await async_session_manager.cleanup_expired(days=7)
    if count > 0:
        logger.info(f"Cleaned up {count} expired sessions")


async def periodic_vacuum():
    """Run SQLite VACUUM to reclaim disk space."""
    from db.database import run_vacuum

    await run_vacuum()
