"""
Migration: Add chat_session_id and kanban_task_id columns to claude_code_sessions.

Strategy: Drop and recreate the table — old sessions have no saved transcripts,
so there is nothing worth preserving.  Base.metadata.create_all() will create
the table with the new FK columns, indexes, etc.

Usage:
    python scripts/migrate_cc_persistence.py
"""

import asyncio
import logging
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from db.database import engine, init_db
from db.models import Base


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    await init_db()

    async with engine.begin() as conn:
        # Drop old table (no valuable data — transcript wasn't saved)
        logger.info("Dropping old claude_code_sessions table (if exists)...")
        await conn.execute(text("DROP TABLE IF EXISTS claude_code_sessions"))

        logger.info("Recreating claude_code_sessions with new FK columns...")
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[Base.metadata.tables["claude_code_sessions"]],
            )
        )

    logger.info(
        "Migration complete: claude_code_sessions table recreated with "
        "chat_session_id and kanban_task_id columns."
    )


if __name__ == "__main__":
    asyncio.run(migrate())
