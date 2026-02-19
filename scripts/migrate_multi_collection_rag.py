#!/usr/bin/env python3
"""Migration: add multi-collection RAG support.

Adds:
- knowledge_collections.base_dir — directory where collection's files are stored
- knowledge_collection_ids (TEXT, JSON array) to chat_sessions, bot_instances,
  widget_instances, whatsapp_instances — for multi-collection RAG selection
"""

import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / "data" / "secretary.db"


def has_column(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns


def migrate() -> None:
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # 1. knowledge_collections.base_dir
    if has_column(cursor, "knowledge_collections", "base_dir"):
        print("OK knowledge_collections.base_dir already exists")
    else:
        cursor.execute(
            "ALTER TABLE knowledge_collections ADD COLUMN base_dir TEXT DEFAULT 'wiki-pages'"
        )
        print("ADDED knowledge_collections.base_dir")

    # 2. knowledge_collection_ids on 4 tables
    tables = ["chat_sessions", "bot_instances", "widget_instances", "whatsapp_instances"]
    for table in tables:
        col = "knowledge_collection_ids"
        if has_column(cursor, table, col):
            print(f"OK {table}.{col} already exists")
        else:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
            print(f"ADDED {table}.{col}")

    conn.commit()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    migrate()
