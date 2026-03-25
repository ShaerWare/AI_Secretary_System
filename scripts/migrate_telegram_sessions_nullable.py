"""Make telegram_sessions.chat_session_id nullable.

Allows registering users before they have a chat session.
"""

import sqlite3
import sys


DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "data/secretary.db"


def migrate(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=OFF")

    # Check current schema
    schema = conn.execute("SELECT sql FROM sqlite_master WHERE name='telegram_sessions'").fetchone()
    if not schema:
        print("telegram_sessions table not found — nothing to do")
        return

    # SQLite doesn't support ALTER COLUMN, so we recreate the table
    conn.executescript("""
        BEGIN;

        CREATE TABLE telegram_sessions_new (
            bot_id VARCHAR(50) NOT NULL DEFAULT 'default',
            user_id INTEGER NOT NULL,
            chat_session_id VARCHAR(50) REFERENCES chat_sessions(id) ON DELETE SET NULL,
            username VARCHAR(100),
            first_name VARCHAR(100),
            last_name VARCHAR(100),
            created DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (bot_id, user_id)
        );

        INSERT INTO telegram_sessions_new
            SELECT bot_id, user_id, chat_session_id, username, first_name, last_name, created, updated
            FROM telegram_sessions;

        DROP TABLE telegram_sessions;

        ALTER TABLE telegram_sessions_new RENAME TO telegram_sessions;

        CREATE INDEX ix_telegram_sessions_bot_user ON telegram_sessions(bot_id, user_id);

        COMMIT;
    """)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.close()
    print(f"Migration done: chat_session_id is now nullable in {db_path}")


if __name__ == "__main__":
    migrate(DB_PATH)
