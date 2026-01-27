#!/usr/bin/env python3
"""
Migration script: JSON files -> SQLite database

This script migrates existing JSON data files to the new SQLite database:
- chat_sessions.json -> chat_sessions + chat_messages tables
- typical_responses.json -> faq_entries table
- custom_presets.json -> tts_presets table
- telegram_config.json -> system_config table
- telegram_sessions.json -> telegram_sessions table
- widget_config.json -> system_config table

Usage:
    python scripts/migrate_json_to_db.py

The script will:
1. Backup existing JSON files to data/backup/
2. Initialize the SQLite database
3. Migrate all data
4. Verify migration
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
    "chat_sessions": BASE_DIR / "chat_sessions.json",
    "typical_responses": BASE_DIR / "typical_responses.json",
    "custom_presets": BASE_DIR / "custom_presets.json",
    "telegram_config": BASE_DIR / "telegram_config.json",
    "telegram_sessions": BASE_DIR / "telegram_sessions.json",
    "widget_config": BASE_DIR / "widget_config.json",
}


def backup_json_files():
    """Backup all JSON files before migration."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    backed_up = []
    for name, path in JSON_FILES.items():
        if path.exists():
            backup_path = BACKUP_DIR / f"{name}_{timestamp}.json"
            shutil.copy(path, backup_path)
            backed_up.append(name)
            logger.info(f"📦 Backed up {path.name} -> {backup_path.name}")

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


async def migrate_chat_sessions(chat_repo):
    """Migrate chat_sessions.json to database."""
    data = load_json_file(JSON_FILES["chat_sessions"])
    if not data:
        logger.info("⏭️ No chat_sessions.json found, skipping")
        return 0

    count = 0
    for session_id, session_data in data.items():
        try:
            # Create session
            from datetime import datetime

            from db.models import ChatMessage, ChatSession

            session = ChatSession(
                id=session_data.get("id", session_id),
                title=session_data.get("title", "Новый чат"),
                system_prompt=session_data.get("system_prompt"),
                created=datetime.fromisoformat(session_data["created"])
                if session_data.get("created")
                else datetime.utcnow(),
                updated=datetime.fromisoformat(session_data["updated"])
                if session_data.get("updated")
                else datetime.utcnow(),
            )
            chat_repo.session.add(session)

            # Create messages
            for msg_data in session_data.get("messages", []):
                message = ChatMessage(
                    id=msg_data.get("id"),
                    session_id=session.id,
                    role=msg_data.get("role"),
                    content=msg_data.get("content", ""),
                    edited=msg_data.get("edited", False),
                    created=datetime.fromisoformat(msg_data["timestamp"])
                    if msg_data.get("timestamp")
                    else datetime.utcnow(),
                )
                chat_repo.session.add(message)

            count += 1
        except Exception as e:
            logger.error(f"Error migrating session {session_id}: {e}")

    await chat_repo.session.commit()
    logger.info(f"✅ Migrated {count} chat sessions")
    return count


async def migrate_faq(faq_repo):
    """Migrate typical_responses.json to database."""
    data = load_json_file(JSON_FILES["typical_responses"])
    if not data:
        logger.info("⏭️ No typical_responses.json found, skipping")
        return 0

    count = await faq_repo.import_from_dict(data)
    logger.info(f"✅ Migrated {count} FAQ entries")
    return count


async def migrate_presets(preset_repo):
    """Migrate custom_presets.json to database."""
    data = load_json_file(JSON_FILES["custom_presets"])
    if not data:
        logger.info("⏭️ No custom_presets.json found, skipping")
        return 0

    count = await preset_repo.import_from_dict(data)
    logger.info(f"✅ Migrated {count} TTS presets")
    return count


async def migrate_telegram_config(config_repo):
    """Migrate telegram_config.json to database."""
    data = load_json_file(JSON_FILES["telegram_config"])
    if not data:
        logger.info("⏭️ No telegram_config.json found, skipping")
        return False

    await config_repo.set_config("telegram", data)
    logger.info("✅ Migrated telegram config")
    return True


async def migrate_telegram_sessions(telegram_repo):
    """Migrate telegram_sessions.json to database."""
    data = load_json_file(JSON_FILES["telegram_sessions"])
    if not data:
        logger.info("⏭️ No telegram_sessions.json found, skipping")
        return 0

    # Convert string keys to int
    sessions = {int(k): v for k, v in data.items()}
    count = await telegram_repo.import_from_dict(sessions)
    logger.info(f"✅ Migrated {count} Telegram sessions")
    return count


async def migrate_widget_config(config_repo):
    """Migrate widget_config.json to database."""
    data = load_json_file(JSON_FILES["widget_config"])
    if not data:
        logger.info("⏭️ No widget_config.json found, skipping")
        return False

    await config_repo.set_config("widget", data)
    logger.info("✅ Migrated widget config")
    return True


async def verify_migration(chat_repo, faq_repo, preset_repo, config_repo, telegram_repo):
    """Verify migration was successful."""
    logger.info("\n📊 Verifying migration...")

    # Check chat sessions
    session_count = await chat_repo.get_session_count()
    message_count = await chat_repo.get_message_count()
    logger.info(f"   Chat sessions: {session_count}, messages: {message_count}")

    # Check FAQ
    faq_stats = await faq_repo.get_stats()
    logger.info(f"   FAQ entries: {faq_stats['total']} ({faq_stats['enabled']} enabled)")

    # Check presets
    preset_counts = await preset_repo.get_preset_count()
    logger.info(f"   TTS presets: {preset_counts['total']} ({preset_counts['custom']} custom)")

    # Check configs
    telegram_config = await config_repo.get_telegram_config()
    widget_config = await config_repo.get_widget_config()
    logger.info(f"   Telegram config: {'present' if telegram_config else 'missing'}")
    logger.info(f"   Widget config: {'present' if widget_config else 'missing'}")

    # Check telegram sessions
    tg_session_count = await telegram_repo.get_session_count()
    logger.info(f"   Telegram sessions: {tg_session_count}")

    return True


async def main():
    """Main migration function."""
    logger.info("🚀 Starting JSON to SQLite migration\n")

    # Step 1: Backup
    logger.info("📦 Step 1: Backing up JSON files")
    backed_up = backup_json_files()
    logger.info(f"   Backed up {len(backed_up)} files\n")

    # Step 2: Initialize database
    logger.info("🗄️ Step 2: Initializing database")
    from db.database import AsyncSessionLocal, init_db

    await init_db()
    logger.info("")

    # Step 3: Run migrations
    logger.info("📥 Step 3: Migrating data")

    async with AsyncSessionLocal() as session:
        from db.repositories import (
            ChatRepository,
            ConfigRepository,
            FAQRepository,
            PresetRepository,
            TelegramRepository,
        )

        chat_repo = ChatRepository(session)
        faq_repo = FAQRepository(session)
        preset_repo = PresetRepository(session)
        config_repo = ConfigRepository(session)
        telegram_repo = TelegramRepository(session)

        await migrate_chat_sessions(chat_repo)
        await migrate_faq(faq_repo)
        await migrate_presets(preset_repo)
        await migrate_telegram_config(config_repo)
        await migrate_telegram_sessions(telegram_repo)
        await migrate_widget_config(config_repo)

        logger.info("")

        # Step 4: Verify
        await verify_migration(chat_repo, faq_repo, preset_repo, config_repo, telegram_repo)

    logger.info("\n✅ Migration complete!")
    logger.info(f"   Database: {DATA_DIR / 'secretary.db'}")
    logger.info(f"   Backups: {BACKUP_DIR}")
    logger.info(
        "\n⚠️ Note: JSON files are kept for reference. You can delete them after verifying the migration."
    )


if __name__ == "__main__":
    asyncio.run(main())
