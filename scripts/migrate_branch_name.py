"""
Add branch_name column to chat_messages table.

Usage:
    python scripts/migrate_branch_name.py
"""

import sqlite3
import sys
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / "data" / "secretary.db"


def migrate(conn: sqlite3.Connection) -> None:
    # Check if column already exists
    cursor = conn.execute("PRAGMA table_info(chat_messages)")
    columns = {row[1] for row in cursor.fetchall()}
    if "branch_name" in columns:
        print("Column branch_name already exists, skipping.")
        return
    conn.execute("ALTER TABLE chat_messages ADD COLUMN branch_name TEXT")
    print("Added branch_name column to chat_messages.")


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
        conn.execute("COMMIT")
        print("Migration completed successfully.")
    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
