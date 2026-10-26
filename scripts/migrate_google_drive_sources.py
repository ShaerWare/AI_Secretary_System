"""
Add source settings to `google_drive_projects`.

A Drive source used to be a one-shot RAG import of a whole folder: no binary
formats, no file selection, no schedule. Supplier price lists live in a shared
Drive folder and get replaced in place, so a source now also says what it feeds
(`purpose`: rag / prices / both), which files (`file_ids`, empty = whole
folder), whether the daily check runs (`auto_sync`), and remembers what it
synced last time (`files_state`, `sync_report`, `last_checked`).

Existing rows keep behaving as before: purpose=rag, whole folder, auto_sync on.

Usage:
    python scripts/migrate_google_drive_sources.py
"""

import sqlite3
import sys
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / "data" / "secretary.db"

COLUMNS = {
    "purpose": "VARCHAR(20) NOT NULL DEFAULT 'rag'",
    "file_ids": "TEXT",
    "auto_sync": "BOOLEAN NOT NULL DEFAULT 1",
    "files_state": "TEXT",
    "sync_report": "TEXT",
    "last_checked": "DATETIME",
}


def migrate(conn: sqlite3.Connection) -> None:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "google_drive_projects" not in tables:
        print("Table google_drive_projects absent — create_all will build it with the new columns")
        return

    cols = {row[1] for row in conn.execute("PRAGMA table_info(google_drive_projects)")}
    added = []
    for name, ddl in COLUMNS.items():
        if name in cols:
            continue
        conn.execute(f"ALTER TABLE google_drive_projects ADD COLUMN {name} {ddl}")
        added.append(name)
    print(f"Added columns: {', '.join(added)}" if added else "All columns present — nothing to do")


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
