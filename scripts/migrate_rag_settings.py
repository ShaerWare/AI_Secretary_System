#!/usr/bin/env python3
"""Migration: Add per-instance RAG configuration columns.

Tables modified:
  - bot_instances       (rag_mode, knowledge_collection_id)
  - widget_instances    (rag_mode, knowledge_collection_id)
  - whatsapp_instances  (rag_mode, knowledge_collection_id)
  - chat_sessions       (rag_mode, knowledge_collection_id)

rag_mode values: "all" (default), "collection", "none"
knowledge_collection_id: FK to knowledge_collections.id (nullable)

Usage:
  python scripts/migrate_rag_settings.py
"""

import sqlite3
import sys
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / "data" / "secretary.db"

TABLES = [
    "bot_instances",
    "widget_instances",
    "whatsapp_instances",
    "chat_sessions",
]

COLUMNS = [
    ("rag_mode", "TEXT DEFAULT 'all'"),
    ("knowledge_collection_id", "INTEGER REFERENCES knowledge_collections(id)"),
]


def has_column(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns


def migrate():
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        print("Start the application first to create the database.")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    for table in TABLES:
        # Check if table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        if not cursor.fetchone():
            print(f"  SKIP  {table} — table does not exist")
            continue

        for col_name, col_def in COLUMNS:
            if has_column(cursor, table, col_name):
                print(f"  OK    {table}.{col_name} — already exists")
                continue

            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                print(f"  ADD   {table}.{col_name} — column created")
            except Exception as e:
                print(f"  ERR   {table}.{col_name} — {e}")

    conn.commit()
    conn.close()
    print("\nMigration complete.")


if __name__ == "__main__":
    migrate()
