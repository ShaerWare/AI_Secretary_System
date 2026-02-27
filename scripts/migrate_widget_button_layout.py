#!/usr/bin/env python3
"""
Migration: Add button_size, button_offset_bottom, button_offset_side to widget_instances.

Safe to run multiple times (checks if columns exist).
"""

import sqlite3
import sys
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / "data" / "secretary.db"

COLUMNS = [
    ("button_size", "INTEGER DEFAULT 60"),
    ("button_offset_bottom", "INTEGER DEFAULT 20"),
    ("button_offset_side", "INTEGER DEFAULT 20"),
]


def migrate():
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        print("Run the app first to create the database.")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    existing = {row[1] for row in cursor.execute("PRAGMA table_info(widget_instances)")}

    added = 0
    for col_name, col_type in COLUMNS:
        if col_name not in existing:
            cursor.execute(f"ALTER TABLE widget_instances ADD COLUMN {col_name} {col_type}")
            print(f"  Added column: {col_name} ({col_type})")
            added += 1
        else:
            print(f"  Column already exists: {col_name}")

    # Preserve current layout for stalkerelectric instance
    cursor.execute(
        "UPDATE widget_instances SET button_size = 70, button_offset_bottom = 70"
        " WHERE id = 'stalkerelectric'"
    )
    if cursor.rowcount:
        print("  Updated 'stalkerelectric' instance to 70px values")

    conn.commit()
    conn.close()

    if added:
        print(f"\nMigration complete: {added} column(s) added.")
    else:
        print("\nNo changes needed — all columns already exist.")


if __name__ == "__main__":
    migrate()
