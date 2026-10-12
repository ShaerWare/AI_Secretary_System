"""
Prompt-only default assistants: rag_mode "all" → "none".

`ensure_default_instances` used to give an assistant without collections
(«Программист») rag_mode="all", which expands to EVERY enabled collection —
the StalkerElectric catalog (id 6) included. That switched on the procurement
offer injection, and the programmer answered «напиши бота для Binance» with
«помогаю только по электротехнике, могу передать менеджеру».

Private sessions copy rag_mode at creation and the stream endpoint resolves
RAG from the session itself, so both the instances and their sessions need
the fix. Scoped to the default catalog ids — custom instances where an admin
chose "all" deliberately are left alone.

Usage:
    python scripts/migrate_prompt_only_assistants_rag.py [--dry-run]
"""

import sqlite3
import sys
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / "data" / "secretary.db"

DEFAULT_ASSISTANT_IDS = (
    "marketer",
    "programmer",
    "lawyer-ru",
    "accountant-ru",
    "lawyer-kz",
    "accountant-kz",
)

_NO_COLLECTIONS = "(knowledge_collection_ids IS NULL OR knowledge_collection_ids IN ('', '[]'))"


def migrate(conn: sqlite3.Connection) -> None:
    marks = ",".join("?" * len(DEFAULT_ASSISTANT_IDS))
    instances = [
        row[0]
        for row in conn.execute(
            f"SELECT id FROM mobile_app_instances "
            f"WHERE id IN ({marks}) AND rag_mode = 'all' AND {_NO_COLLECTIONS}",
            DEFAULT_ASSISTANT_IDS,
        )
    ]
    print(f"Instances to fix: {instances or 'none'}")
    if not instances:
        return

    imarks = ",".join("?" * len(instances))
    conn.execute(
        f"UPDATE mobile_app_instances SET rag_mode = 'none' WHERE id IN ({imarks})",
        instances,
    )
    cur = conn.execute(
        f"UPDATE chat_sessions SET rag_mode = 'none' "
        f"WHERE source = 'mobile' AND source_id IN ({imarks}) "
        f"AND rag_mode = 'all' AND {_NO_COLLECTIONS}",
        instances,
    )
    print(f"Sessions fixed: {cur.rowcount}")


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
        migrate(conn)
        if dry_run:
            conn.rollback()
            print("Dry run — rolled back")
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
