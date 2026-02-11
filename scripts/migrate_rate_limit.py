#!/usr/bin/env python3
"""
Migration: Add per-instance rate limiting fields.

Adds columns to bot_instances and widget_instances:
  - rate_limit_count (INTEGER) — max messages per window
  - rate_limit_hours (INTEGER) — time window in hours

Sets default 5/5 on all existing rows.

Safe to run multiple times (checks if columns exist).
"""

import sqlite3
import sys
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / "data" / "secretary.db"

TABLES = ["bot_instances", "widget_instances"]
COLUMNS = [
    ("rate_limit_count", "INTEGER"),
    ("rate_limit_hours", "INTEGER"),
]


def migrate():
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        print("Run the app first to create the database.")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    total_added = 0

    for table in TABLES:
        print(f"\n--- {table} ---")
        existing = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}

        for col_name, col_type in COLUMNS:
            if col_name not in existing:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
                print(f"  Added column: {col_name} ({col_type})")
                total_added += 1
            else:
                print(f"  Column already exists: {col_name}")

        # Set defaults on existing rows that have NULL
        cursor.execute(f"UPDATE {table} SET rate_limit_count = 5 WHERE rate_limit_count IS NULL")
        cursor.execute(f"UPDATE {table} SET rate_limit_hours = 5 WHERE rate_limit_hours IS NULL")
        updated = cursor.rowcount
        print(f"  Set default 5/5 on {updated} row(s)")

    conn.commit()
    conn.close()

    if total_added:
        print(f"\nMigration complete: {total_added} column(s) added.")
    else:
        print("\nNo changes needed — all columns already exist.")


if __name__ == "__main__":
    print("Migrating bot_instances and widget_instances for rate limiting...")
    migrate()
