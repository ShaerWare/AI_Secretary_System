"""
Add extra_data column to chat_messages for image metadata.

Usage:
    python scripts/migrate_add_extra_data_to_chat_messages.py
"""

import sqlite3
import sys
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / "data" / "secretary.db"


def migrate(conn: sqlite3.Connection) -> None:
    """Add extra_data TEXT column to chat_messages if not exists."""
    cols = [row[1] for row in conn.execute("PRAGMA table_info(chat_messages)").fetchall()]
    if "extra_data" in cols:
        print("Column extra_data already exists — skipping")
        return
    conn.execute("ALTER TABLE chat_messages ADD COLUMN extra_data TEXT")
    print("Added extra_data column to chat_messages")


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
        print(f"Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
