"""
Migration: add chat_session_prompts table for multi-role prompt switching.

Creates a named-prompt table attached to each chat session. Existing
``chat_sessions.system_prompt`` values are copied into a single active
prompt (with NULL name) so behaviour is preserved; the column itself
stays in place and continues to mirror the active prompt content.
"""

import sqlite3
import sys
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / "data" / "secretary.db"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def migrate(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, "chat_session_prompts"):
        print("OK chat_session_prompts already exists — skipping create")
    else:
        conn.execute(
            """
            CREATE TABLE chat_session_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id VARCHAR(50) NOT NULL,
                name VARCHAR(100),
                content TEXT NOT NULL DEFAULT '',
                is_active BOOLEAN NOT NULL DEFAULT 0,
                position INTEGER NOT NULL DEFAULT 0,
                created DATETIME,
                updated DATETIME,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX ix_chat_session_prompts_session_id ON chat_session_prompts(session_id)"
        )
        conn.execute(
            "CREATE INDEX ix_chat_session_prompts_session_position "
            "ON chat_session_prompts(session_id, position)"
        )
        print("ADDED chat_session_prompts table")

    cur = conn.execute(
        """
        SELECT s.id, s.system_prompt
        FROM chat_sessions s
        LEFT JOIN chat_session_prompts p ON p.session_id = s.id
        WHERE s.system_prompt IS NOT NULL
          AND TRIM(s.system_prompt) <> ''
          AND p.id IS NULL
        """
    )
    rows = cur.fetchall()
    if rows:
        conn.executemany(
            """
            INSERT INTO chat_session_prompts
                (session_id, name, content, is_active, position, created, updated)
            VALUES (?, NULL, ?, 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            [(sid, prompt or "") for sid, prompt in rows],
        )
        print(f"SEEDED {len(rows)} prompt(s) from existing chat_sessions.system_prompt")
    else:
        print("OK no sessions required seeding")


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
