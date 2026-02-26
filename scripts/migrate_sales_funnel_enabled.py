#!/usr/bin/env python3
"""
Migration: add sales_funnel_enabled column to bot_instances table.

This column controls whether the Telegram bot runs the sales funnel
(quiz, segments, follow-ups) and the news broadcast scheduler.
Default: True (enabled) — matches the SQLAlchemy model default.

Usage:
    python scripts/migrate_sales_funnel_enabled.py
"""

import sqlite3
import sys
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / "data" / "secretary.db"


def migrate() -> None:
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Check if column already exists
    cursor.execute("PRAGMA table_info(bot_instances)")
    columns = [row[1] for row in cursor.fetchall()]

    if "sales_funnel_enabled" in columns:
        print("Column 'sales_funnel_enabled' already exists in bot_instances. Nothing to do.")
        conn.close()
        return

    print("Adding 'sales_funnel_enabled' column to bot_instances...")
    cursor.execute(
        "ALTER TABLE bot_instances ADD COLUMN sales_funnel_enabled BOOLEAN NOT NULL DEFAULT 1"
    )
    conn.commit()

    # Verify
    cursor.execute("PRAGMA table_info(bot_instances)")
    columns = [row[1] for row in cursor.fetchall()]
    assert "sales_funnel_enabled" in columns, "Column was not added!"

    print("Done. Column 'sales_funnel_enabled' added (default=True for all existing bots).")
    conn.close()


if __name__ == "__main__":
    migrate()
