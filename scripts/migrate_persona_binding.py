"""Persona binding migration.

Two things:

1. ``chat_sessions.llm_persona`` — new nullable column linking a chat to an
   ``llm_presets`` row (persona). NULL = no persona.

2. Existing ``llm_persona`` values on widget / mobile / bot instances are
   reset to ``''`` (= "no persona"). Until now that column was written by the
   admin panel but read by nothing, so every instance carries a stale default
   of ``'anna'``. Honouring it retroactively would silently swap the system
   prompt and generation parameters of every live widget and bot. Clearing it
   keeps today's behaviour; the admin re-attaches a persona explicitly where
   it is wanted.

Idempotent: safe to re-run.

Usage:
    python scripts/migrate_persona_binding.py [--dry-run]
"""

import sqlite3
import sys
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / "data" / "secretary.db"

INSTANCE_TABLES = ("widget_instances", "mobile_app_instances", "bot_instances")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    return column in cols


def migrate(conn: sqlite3.Connection, dry_run: bool = False) -> None:
    # 1. chat_sessions.llm_persona
    if not _table_exists(conn, "chat_sessions"):
        print("! chat_sessions table missing — skipping column add")
    elif _column_exists(conn, "chat_sessions", "llm_persona"):
        print("= chat_sessions.llm_persona already exists")
    else:
        print("+ chat_sessions.llm_persona (TEXT NULL)")
        if not dry_run:
            conn.execute("ALTER TABLE chat_sessions ADD COLUMN llm_persona VARCHAR(50)")

    # 2. Clear stale persona defaults on channel instances
    for table in INSTANCE_TABLES:
        if not _table_exists(conn, table) or not _column_exists(conn, table, "llm_persona"):
            print(f"= {table}: no llm_persona column, skipped")
            continue
        (stale,) = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE llm_persona IS NOT NULL AND llm_persona != ''"
        ).fetchone()
        if not stale:
            print(f"= {table}: nothing to clear")
            continue
        print(f"~ {table}: clearing llm_persona on {stale} row(s)")
        if not dry_run:
            conn.execute(
                f"UPDATE {table} SET llm_persona = '' "
                "WHERE llm_persona IS NOT NULL AND llm_persona != ''"
            )


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")

    try:
        conn.execute("BEGIN IMMEDIATE")
        migrate(conn, dry_run=dry_run)
        if dry_run:
            conn.rollback()
            print("Dry run — no changes written")
        else:
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
