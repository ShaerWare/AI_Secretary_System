#!/usr/bin/env python3
"""
Migration script: Migrate to multi-instance bots and widgets

This script migrates existing configuration to the new multi-instance architecture:
- telegram_config.json -> bot_instances table ("default" instance)
- widget_config.json -> widget_instances table ("default" instance)
- telegram_sessions -> updates existing records with bot_id="default"

The script preserves backward compatibility:
- Old API endpoints continue to work with the "default" instance
- Existing telegram_sessions are associated with "default" bot

Usage:
    python scripts/migrate_to_instances.py

The script is idempotent - running it multiple times is safe.
"""

import asyncio
import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path


# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# File paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
BACKUP_DIR = DATA_DIR / "backup"

JSON_FILES = {
    "telegram_config": BASE_DIR / "telegram_config.json",
    "widget_config": BASE_DIR / "widget_config.json",
    "telegram_sessions": BASE_DIR / "telegram_sessions.json",
}


def backup_json_files():
    """Backup JSON files before migration."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    backed_up = []
    for name, path in JSON_FILES.items():
        if path.exists():
            backup_path = BACKUP_DIR / f"{name}_instances_migration_{timestamp}.json"
            shutil.copy(path, backup_path)
            backed_up.append(name)
            logger.info(f"Backed up {path.name} -> {backup_path.name}")

    return backed_up


def load_json_file(path: Path) -> dict | list | None:
    """Load JSON file, return None if doesn't exist."""
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {path}: {e}")
        return None


async def migrate_bot_instance(bot_repo):
    """Migrate telegram_config.json to default bot instance."""
    data = load_json_file(JSON_FILES["telegram_config"])
    if not data:
        logger.info("No telegram_config.json found, creating default bot instance")
        data = {}

    # Check if default instance already exists
    existing = await bot_repo.get_instance("default")
    if existing:
        logger.info("Default bot instance already exists, skipping creation")
        return existing

    # Import from legacy config
    instance = await bot_repo.import_from_legacy_config(data, instance_id="default")
    logger.info("Created default bot instance from telegram_config.json")
    return instance


async def migrate_widget_instance(widget_repo):
    """Migrate widget_config.json to default widget instance."""
    data = load_json_file(JSON_FILES["widget_config"])
    if not data:
        logger.info("No widget_config.json found, creating default widget instance")
        data = {}

    # Check if default instance already exists
    existing = await widget_repo.get_instance("default")
    if existing:
        logger.info("Default widget instance already exists, skipping creation")
        return existing

    # Import from legacy config
    instance = await widget_repo.import_from_legacy_config(data, instance_id="default")
    logger.info("Created default widget instance from widget_config.json")
    return instance


async def add_bot_id_column_if_missing():
    """Add bot_id column to telegram_sessions table if it doesn't exist."""
    from sqlalchemy import text

    from db.database import engine

    async with engine.begin() as conn:
        # Check if column exists
        result = await conn.execute(text("PRAGMA table_info(telegram_sessions)"))
        columns = [row[1] for row in result.fetchall()]

        if "bot_id" not in columns:
            logger.info("Adding bot_id column to telegram_sessions table...")
            # SQLite doesn't support adding PRIMARY KEY columns easily
            # So we need to:
            # 1. Create new table with correct schema
            # 2. Copy data
            # 3. Drop old table
            # 4. Rename new table

            # Create new table
            await conn.execute(
                text("""
                CREATE TABLE telegram_sessions_new (
                    bot_id VARCHAR(50) NOT NULL DEFAULT 'default',
                    user_id INTEGER NOT NULL,
                    chat_session_id VARCHAR(100) NOT NULL,
                    username VARCHAR(100),
                    first_name VARCHAR(100),
                    last_name VARCHAR(100),
                    created DATETIME,
                    updated DATETIME,
                    PRIMARY KEY (bot_id, user_id)
                )
            """)
            )

            # Copy data with default bot_id
            await conn.execute(
                text("""
                INSERT INTO telegram_sessions_new (bot_id, user_id, chat_session_id, username, first_name, last_name, created, updated)
                SELECT 'default', user_id, chat_session_id, username, first_name, last_name, created, updated
                FROM telegram_sessions
            """)
            )

            # Drop old table
            await conn.execute(text("DROP TABLE telegram_sessions"))

            # Rename new table
            await conn.execute(
                text("ALTER TABLE telegram_sessions_new RENAME TO telegram_sessions")
            )

            logger.info("Added bot_id column and migrated existing sessions to 'default'")
            return True
        else:
            logger.info("bot_id column already exists in telegram_sessions")
            return False


async def migrate_telegram_sessions(telegram_repo):
    """Ensure all telegram sessions have bot_id set to 'default'."""
    # First, ensure the bot_id column exists
    await add_bot_id_column_if_missing()

    # The database schema now has bot_id with default="default"
    # Sessions should already be migrated by the column addition above
    logger.info("Telegram sessions migration complete")
    return 0


async def verify_migration(bot_repo, widget_repo, telegram_repo):
    """Verify migration was successful."""
    logger.info("\nVerifying migration...")

    # Check bot instances
    bot_instances = await bot_repo.list_instances()
    logger.info(f"   Bot instances: {len(bot_instances)}")
    for inst in bot_instances:
        logger.info(f"      - {inst['id']}: {inst['name']} (enabled={inst['enabled']})")

    # Check widget instances
    widget_instances = await widget_repo.list_instances()
    logger.info(f"   Widget instances: {len(widget_instances)}")
    for inst in widget_instances:
        logger.info(f"      - {inst['id']}: {inst['name']} (enabled={inst['enabled']})")

    # Check telegram sessions by bot
    session_counts = await telegram_repo.get_session_count_by_bot()
    logger.info("   Telegram sessions by bot:")
    for bot_id, count in session_counts.items():
        logger.info(f"      - {bot_id}: {count} sessions")

    return True


async def main():
    """Main migration function."""
    logger.info("Starting multi-instance migration\n")

    # Step 1: Backup
    logger.info("Step 1: Backing up JSON files")
    backed_up = backup_json_files()
    logger.info(f"   Backed up {len(backed_up)} files\n")

    # Step 2: Initialize/update database
    logger.info("Step 2: Initializing database")
    from db.database import AsyncSessionLocal, init_db

    await init_db()
    logger.info("   Database tables created/verified\n")

    # Step 3: Run migrations
    logger.info("Step 3: Migrating data to instances")

    async with AsyncSessionLocal() as session:
        from db.repositories import (
            TelegramRepository,
        )
        from db.repositories.bot_instance import BotInstanceRepository
        from db.repositories.widget_instance import WidgetInstanceRepository

        bot_repo = BotInstanceRepository(session)
        widget_repo = WidgetInstanceRepository(session)
        telegram_repo = TelegramRepository(session)

        # Migrate bot instance
        await migrate_bot_instance(bot_repo)

        # Migrate widget instance
        await migrate_widget_instance(widget_repo)

        # Migrate telegram sessions
        await migrate_telegram_sessions(telegram_repo)

        logger.info("")

        # Step 4: Verify
        await verify_migration(bot_repo, widget_repo, telegram_repo)

    logger.info("\nMigration complete!")
    logger.info(f"   Database: {DATA_DIR / 'secretary.db'}")
    logger.info(f"   Backups: {BACKUP_DIR}")
    logger.info("\nNext steps:")
    logger.info("   1. Start the orchestrator: ./start_gpu.sh")
    logger.info("   2. Access Admin Panel: http://localhost:8002/admin/")
    logger.info("   3. Go to Telegram tab to manage bot instances")
    logger.info("   4. Go to Widget tab to manage widget instances")
    logger.info("\nBackward compatibility:")
    logger.info("   - Old /admin/telegram/config endpoint works with 'default' instance")
    logger.info("   - Old /admin/widget/config endpoint works with 'default' instance")
    logger.info("   - Existing telegram sessions are associated with 'default' bot")


if __name__ == "__main__":
    asyncio.run(main())
