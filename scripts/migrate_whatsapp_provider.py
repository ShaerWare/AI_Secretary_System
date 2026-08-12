"""
Add self-hosted-provider columns to whatsapp_instances.

Introduces:
    provider      "cloud" (Meta Cloud API, existing behaviour) | "bridge"
                  (services/whatsapp-bridge — a phone linked by QR)
    bridge_url    optional per-instance bridge location
    bridge_token  optional per-instance shared secret

Existing rows are pinned to "cloud" so nothing changes transport under a
running bot.

Usage:
    python scripts/migrate_whatsapp_provider.py
"""

import sqlite3
import sys
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / "data" / "secretary.db"

TABLE = "whatsapp_instances"

NEW_COLUMNS = [
    ("provider", "VARCHAR(20) NOT NULL DEFAULT 'cloud'"),
    ("bridge_url", "VARCHAR(255)"),
    ("bridge_token", "VARCHAR(255)"),
]


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def migrate(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, TABLE):
        print(f"Table {TABLE} does not exist — nothing to migrate")
        return

    columns = _existing_columns(conn, TABLE)

    for name, ddl in NEW_COLUMNS:
        if name in columns:
            print(f"  = {name} already present, skipping")
            continue
        conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN {name} {ddl}")
        print(f"  + {name}")

    # Rows created before this migration keep the Cloud API transport.
    updated = conn.execute(
        f"UPDATE {TABLE} SET provider = 'cloud' WHERE provider IS NULL OR provider = ''"
    ).rowcount
    if updated:
        print(f"  ~ pinned {updated} existing instance(s) to provider='cloud'")


def main() -> None:
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")

    try:
        conn.execute("BEGIN IMMEDIATE")
        migrate(conn)
        conn.commit()
        print("Migration completed successfully")
    except Exception as e:
        conn.rollback()
        print(f"Migration FAILED, rolled back: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
