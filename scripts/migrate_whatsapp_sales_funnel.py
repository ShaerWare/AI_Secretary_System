"""
Add `whatsapp_instances.sales_funnel_enabled` (default 0 = off).

The WhatsApp bot's own-product funnel (AI Secretary pitch, quiz, platform FAQ)
used to be hardcoded on, so a client's assistant answered their customers'
"привет" with an ad for our product. The flag makes it opt-in, mirroring
`telegram_instances.sales_funnel_enabled` — except the default is OFF here:
every existing WhatsApp instance is a client's. Switch it on in the admin panel
for our own marketing numbers.

Usage:
    python scripts/migrate_whatsapp_sales_funnel.py
"""

import sqlite3
import sys
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / "data" / "secretary.db"


def migrate(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(whatsapp_instances)")}
    if "sales_funnel_enabled" in cols:
        print("Column sales_funnel_enabled already present — nothing to do")
        return

    conn.execute(
        "ALTER TABLE whatsapp_instances ADD COLUMN sales_funnel_enabled BOOLEAN NOT NULL DEFAULT 0"
    )
    affected = conn.execute("SELECT COUNT(*) FROM whatsapp_instances").fetchone()[0]
    print(f"Added sales_funnel_enabled=0 to {affected} WhatsApp instance(s)")


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
