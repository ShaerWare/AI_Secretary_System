#!/usr/bin/env python3
"""Migration: create github_repo_projects table + rename Default collection.

Idempotent — safe to run multiple times.
"""

import sqlite3
import sys
from pathlib import Path


DB_PATH = Path("data/secretary.db")


def migrate():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # 1. Create table if not exists
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='github_repo_projects'"
    )
    if cursor.fetchone():
        print("Table github_repo_projects already exists, skipping create.")
    else:
        cursor.execute("""
            CREATE TABLE github_repo_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(200) NOT NULL,
                github_owner VARCHAR(100) NOT NULL,
                github_repo VARCHAR(100) NOT NULL,
                github_token VARCHAR(500),
                branch VARCHAR(100) DEFAULT 'main',
                collection_id INTEGER REFERENCES knowledge_collections(id),
                sync_status VARCHAR(20) DEFAULT 'idle',
                sync_error TEXT,
                last_synced DATETIME,
                last_commit_sha VARCHAR(40),
                include_patterns TEXT,
                exclude_patterns TEXT,
                file_count INTEGER DEFAULT 0,
                total_size_bytes INTEGER DEFAULT 0,
                workspace_id INTEGER DEFAULT 1 REFERENCES workspaces(id),
                created DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        print("Created table github_repo_projects")

    # 2. Rename Default collection to "AI Secretary System"
    cursor.execute("SELECT name FROM knowledge_collections WHERE slug = 'default'")
    row = cursor.fetchone()
    if row:
        if row[0] == "AI Secretary System":
            print("Default collection already renamed to 'AI Secretary System', skipping.")
        else:
            cursor.execute(
                "UPDATE knowledge_collections SET name = 'AI Secretary System' WHERE slug = 'default'"
            )
            conn.commit()
            print(f"Renamed collection '{row[0]}' -> 'AI Secretary System'")
    else:
        print("No collection with slug='default' found, skipping rename.")

    conn.close()


if __name__ == "__main__":
    migrate()
