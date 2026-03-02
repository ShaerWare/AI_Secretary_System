"""Tests for sales DB WAL checkpoint on close and default path changes."""

import sqlite3
from pathlib import Path

import pytest

from telegram_bot.sales.database import SalesDatabase as TelegramSalesDB
from whatsapp_bot.sales.database import SalesDatabase as WhatsAppSalesDB


pytestmark = pytest.mark.asyncio


async def test_telegram_sales_close_checkpoints(tmp_path):
    """Telegram sales DB close() should WAL-checkpoint before closing."""
    db_path = tmp_path / "test_sales.db"
    db = TelegramSalesDB(str(db_path))
    await db.init()

    # Insert data to create WAL entries
    await db.upsert_user(1, username="test")
    await db.close()

    # After close with TRUNCATE checkpoint, WAL should be empty/absent
    wal = Path(str(db_path) + "-wal")
    if wal.exists():
        assert wal.stat().st_size == 0

    # Verify data persisted in main DB
    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT username FROM users WHERE user_id = 1").fetchone()
    assert row[0] == "test"
    conn.close()


async def test_whatsapp_sales_close_checkpoints(tmp_path):
    """WhatsApp sales DB close() should WAL-checkpoint before closing."""
    db_path = tmp_path / "test_wa_sales.db"
    db = WhatsAppSalesDB(str(db_path))
    await db.init()

    await db.upsert_user("phone123")
    await db.close()

    wal = Path(str(db_path) + "-wal")
    if wal.exists():
        assert wal.stat().st_size == 0

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT user_id FROM users WHERE user_id = 'phone123'").fetchone()
    assert row is not None
    conn.close()


def test_telegram_sales_default_path():
    """Default Telegram sales DB path should be data/sales.db."""
    db = TelegramSalesDB()
    assert db._db_path == "data/sales.db"


def test_whatsapp_sales_default_path():
    """Default WhatsApp sales DB path should be data/wa_sales.db."""
    db = WhatsAppSalesDB()
    assert db._db_path == "data/wa_sales.db"


async def test_telegram_legacy_migration(tmp_path, monkeypatch):
    """Legacy sales.db should be migrated to data/sales.db on init."""
    # Create legacy DB in project root (simulated by tmp_path)
    monkeypatch.chdir(tmp_path)
    legacy_db = tmp_path / "sales.db"
    conn = sqlite3.connect(str(legacy_db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE test (id INTEGER)")
    conn.execute("INSERT INTO test VALUES (99)")
    conn.commit()
    conn.close()

    # Create a fake WAL sidecar
    legacy_wal = tmp_path / "sales.db-wal"
    legacy_wal.write_bytes(b"wal data")

    db = TelegramSalesDB("data/sales.db")
    await db.init()
    await db.close()

    # Legacy file should be gone, new path should exist
    assert not legacy_db.exists()
    assert (tmp_path / "data" / "sales.db").exists()

    # Verify data migrated
    conn = sqlite3.connect(str(tmp_path / "data" / "sales.db"))
    row = conn.execute("SELECT id FROM test").fetchone()
    assert row[0] == 99
    conn.close()


async def test_telegram_close_idempotent(tmp_path):
    """Calling close() twice should not raise."""
    db_path = tmp_path / "test_sales.db"
    db = TelegramSalesDB(str(db_path))
    await db.init()
    await db.close()
    await db.close()  # Should not raise
