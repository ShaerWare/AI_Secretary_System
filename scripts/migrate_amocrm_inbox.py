#!/usr/bin/env python3
"""Migration: add amojo (chat messaging) columns to amocrm_config table.

Adds columns:
  - amojo_base_url TEXT DEFAULT 'https://amojo.amocrm.ru'
  - amojo_scope_id TEXT
  - amojo_channel_secret TEXT
"""

import sqlite3


DB_PATH = "data/secretary.db"


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='amocrm_config'")
    if not cursor.fetchone():
        print("Table amocrm_config does not exist yet, skipping migration.")
        conn.close()
        return

    # Get existing columns
    cursor.execute("PRAGMA table_info(amocrm_config)")
    columns = {row[1] for row in cursor.fetchall()}

    added = []

    if "amojo_base_url" not in columns:
        cursor.execute(
            "ALTER TABLE amocrm_config ADD COLUMN amojo_base_url TEXT DEFAULT 'https://amojo.amocrm.ru'"
        )
        added.append("amojo_base_url")

    if "amojo_scope_id" not in columns:
        cursor.execute("ALTER TABLE amocrm_config ADD COLUMN amojo_scope_id TEXT")
        added.append("amojo_scope_id")

    if "amojo_channel_secret" not in columns:
        cursor.execute("ALTER TABLE amocrm_config ADD COLUMN amojo_channel_secret TEXT")
        added.append("amojo_channel_secret")

    conn.commit()
    conn.close()

    if added:
        print(f"Added columns: {', '.join(added)}")
    else:
        print("All amojo columns already exist.")


if __name__ == "__main__":
    migrate()
