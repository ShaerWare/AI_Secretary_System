#!/usr/bin/env python3
"""
Migration: Add knowledge_collections table and collection_id FK to knowledge_documents.

Creates:
- knowledge_collections table (id, name, slug, description, enabled, created, updated)
- Adds collection_id column to knowledge_documents
- Seeds default collection
- Assigns existing documents to default collection

Usage:
    python scripts/migrate_knowledge_collections.py
"""

import sqlite3
import sys
from pathlib import Path


DB_PATH = Path("data/secretary.db")


def migrate():
    if not DB_PATH.exists():
        print(f"❌ Database not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    try:
        # 1. Create knowledge_collections table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_collections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(200) NOT NULL UNIQUE,
                slug VARCHAR(100) NOT NULL UNIQUE,
                description TEXT,
                enabled BOOLEAN NOT NULL DEFAULT 1,
                created DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✅ Created knowledge_collections table")

        # 2. Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS ix_knowledge_collections_name
            ON knowledge_collections (name)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS ix_knowledge_collections_slug
            ON knowledge_collections (slug)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS ix_knowledge_collections_enabled
            ON knowledge_collections (enabled)
        """)
        print("✅ Created indexes")

        # 3. Add collection_id column to knowledge_documents (if not exists)
        cursor.execute("PRAGMA table_info(knowledge_documents)")
        columns = [row[1] for row in cursor.fetchall()]

        if "collection_id" not in columns:
            cursor.execute("""
                ALTER TABLE knowledge_documents
                ADD COLUMN collection_id INTEGER REFERENCES knowledge_collections(id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS ix_knowledge_documents_collection_id
                ON knowledge_documents (collection_id)
            """)
            print("✅ Added collection_id column to knowledge_documents")
        else:
            print("ℹ️ collection_id column already exists")

        # 4. Seed default collection
        cursor.execute(
            "SELECT id FROM knowledge_collections WHERE slug = ?", ("default",)
        )
        row = cursor.fetchone()

        if row:
            default_id = row[0]
            print(f"ℹ️ Default collection already exists (id={default_id})")
        else:
            cursor.execute(
                """
                INSERT INTO knowledge_collections (name, slug, description, enabled)
                VALUES (?, ?, ?, ?)
                """,
                ("Default", "default", "Коллекция по умолчанию", 1),
            )
            default_id = cursor.lastrowid
            print(f"✅ Seeded default collection (id={default_id})")

        # 5. Assign existing documents to default collection
        cursor.execute(
            "UPDATE knowledge_documents SET collection_id = ? WHERE collection_id IS NULL",
            (default_id,),
        )
        assigned = cursor.rowcount
        if assigned:
            print(f"✅ Assigned {assigned} existing documents to default collection")
        else:
            print("ℹ️ No orphaned documents to assign")

        conn.commit()
        print("\n✅ Migration complete!")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
