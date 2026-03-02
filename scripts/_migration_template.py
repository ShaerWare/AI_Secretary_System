"""
Migration template — copy this file for new data migrations.

Usage:
    cp scripts/_migration_template.py scripts/migrate_<name>.py
    # Edit migrate() function, then:
    python scripts/migrate_<name>.py

All SQL inside migrate() runs within a single IMMEDIATE transaction.
If anything fails, the entire migration is rolled back — no partial state.
"""

import sqlite3
import sys
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / "data" / "secretary.db"


def migrate(conn: sqlite3.Connection) -> None:
    """All migration logic here. Runs inside a transaction.

    Example:
        conn.execute("ALTER TABLE ... ADD COLUMN ...")
        conn.execute("UPDATE ... SET ...")
    """
    raise NotImplementedError("Edit this function before running")


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
