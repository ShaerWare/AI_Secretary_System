#!/usr/bin/env python3
"""Migration: add amoCRM lead tracking columns to chat_sessions.

Adds: amocrm_lead_id, amocrm_contact_id, visitor_metadata.
Idempotent — safe to run multiple times.
"""

import sqlite3
import sys
from pathlib import Path


DB_PATH = Path("data/secretary.db")

COLUMNS = [
    ("amocrm_lead_id", "INTEGER"),
    ("amocrm_contact_id", "INTEGER"),
    ("visitor_metadata", "TEXT"),
]


def migrate():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Get existing columns
    cursor.execute("PRAGMA table_info(chat_sessions)")
    existing = {row[1] for row in cursor.fetchall()}

    added = 0
    for col_name, col_type in COLUMNS:
        if col_name not in existing:
            cursor.execute(f"ALTER TABLE chat_sessions ADD COLUMN {col_name} {col_type}")
            print(f"  Added column: {col_name} {col_type}")
            added += 1
        else:
            print(f"  Column {col_name} already exists, skipping.")

    conn.commit()
    conn.close()

    if added:
        print(f"Migration complete: added {added} column(s) to chat_sessions.")
    else:
        print("Nothing to migrate — all columns already exist.")


if __name__ == "__main__":
    migrate()
