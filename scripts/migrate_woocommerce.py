#!/usr/bin/env python3
"""Migration: create woocommerce_config table.

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

    # Check if table already exists
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='woocommerce_config'"
    )
    if cursor.fetchone():
        print("Table woocommerce_config already exists, skipping.")
        conn.close()
        return

    cursor.execute("""
        CREATE TABLE woocommerce_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_url VARCHAR(500) DEFAULT '',
            consumer_key VARCHAR(500) DEFAULT '',
            consumer_secret VARCHAR(500) DEFAULT '',
            is_connected BOOLEAN DEFAULT 0,
            sync_enabled BOOLEAN DEFAULT 1,
            last_sync_at VARCHAR(50),
            products_count INTEGER DEFAULT 0,
            categories_count INTEGER DEFAULT 0,
            orders_count INTEGER DEFAULT 0,
            workspace_id INTEGER DEFAULT 1 REFERENCES workspaces(id),
            created DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    print("Created table woocommerce_config")


if __name__ == "__main__":
    migrate()
