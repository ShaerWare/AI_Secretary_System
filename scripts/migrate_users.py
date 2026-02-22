#!/usr/bin/env python3
"""Migration script for users table.

Creates:
- users: System users with role-based access

Seeds default accounts:
- admin / admin (role=admin)
- demo / demo (role=guest)

Usage: python scripts/migrate_users.py
"""

import sqlite3
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.password import hash_password


DB_PATH = Path(__file__).parent.parent / "data" / "secretary.db"

TABLE_DDL = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username VARCHAR(100) UNIQUE NOT NULL,
        password_hash VARCHAR(128) NOT NULL,
        salt VARCHAR(64) NOT NULL,
        role VARCHAR(20) NOT NULL DEFAULT 'user',
        display_name VARCHAR(200),
        is_active BOOLEAN DEFAULT 1,
        created DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_login DATETIME
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)",
    "CREATE INDEX IF NOT EXISTS ix_users_is_active ON users (is_active)",
]


def seed_user(cursor, username: str, password: str, role: str, display_name: str) -> None:
    """Insert a user if they don't already exist."""
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        print(f"  User '{username}' already exists, skipping")
        return

    pw_hash, salt = hash_password(password)
    cursor.execute(
        """INSERT INTO users (username, password_hash, salt, role, display_name, is_active)
           VALUES (?, ?, ?, ?, ?, 1)""",
        (username, pw_hash, salt, role, display_name),
    )
    print(f"  Created user '{username}' (role={role})")


def migrate() -> None:
    if not DB_PATH.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    print("Creating users table...")
    for ddl in TABLE_DDL:
        cursor.execute(ddl)

    print("Seeding default accounts...")
    seed_user(cursor, "admin", "admin", "admin", "Администратор")
    seed_user(cursor, "demo", "demo", "guest", "Демо")

    conn.commit()
    conn.close()
    print(f"Done. Database: {DB_PATH}")


if __name__ == "__main__":
    migrate()
