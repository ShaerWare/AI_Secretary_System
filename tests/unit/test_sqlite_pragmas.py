"""Verify SQLite PRAGMA initialization for all database engines.

Tests cover:
- Main SQLAlchemy engine (event listener pattern from db/database.py)
- Sales bot databases (aiosqlite direct PRAGMA pattern)
- FK enforcement, PRAGMA persistence across sessions, WAL checkpoint on close
"""

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError as SAIntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool


pytestmark = pytest.mark.asyncio


# ── Main engine PRAGMA tests ──────────────────────────────────────


async def test_main_engine_pragmas(test_engine, test_session_factory):
    """After connecting, engine must have WAL, FK, busy_timeout=5000, synchronous=NORMAL."""
    async with test_session_factory() as session:
        journal = (await session.execute(text("PRAGMA journal_mode"))).scalar()
        fk = (await session.execute(text("PRAGMA foreign_keys"))).scalar()
        busy = (await session.execute(text("PRAGMA busy_timeout"))).scalar()
        sync = (await session.execute(text("PRAGMA synchronous"))).scalar()

    assert journal == "wal"
    assert fk == 1
    assert busy == 5000
    assert sync == 1  # NORMAL


async def test_pragmas_persist_across_sessions(test_session_factory):
    """With StaticPool, PRAGMA values must persist across session creations."""
    for _ in range(3):
        async with test_session_factory() as session:
            fk = (await session.execute(text("PRAGMA foreign_keys"))).scalar()
            journal = (await session.execute(text("PRAGMA journal_mode"))).scalar()
        assert fk == 1
        assert journal == "wal"


async def test_foreign_keys_enforced(test_engine, test_session_factory):
    """INSERT with invalid FK must fail when foreign_keys=ON."""
    # Create parent and child tables with FK constraint
    async with test_engine.begin() as conn:
        await conn.execute(text("CREATE TABLE IF NOT EXISTS parent (id INTEGER PRIMARY KEY)"))
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS child "
                "(id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL, "
                "FOREIGN KEY (parent_id) REFERENCES parent(id))"
            )
        )

    # Valid FK — should succeed
    async with test_session_factory() as session:
        await session.execute(text("INSERT INTO parent (id) VALUES (1)"))
        await session.execute(text("INSERT INTO child (id, parent_id) VALUES (1, 1)"))
        await session.commit()

    # Invalid FK — must raise IntegrityError
    async with test_session_factory() as session:
        with pytest.raises(SAIntegrityError):
            await session.execute(text("INSERT INTO child (id, parent_id) VALUES (2, 999)"))
            await session.commit()


async def test_wal_checkpoint_on_close(tmp_path):
    """After WAL checkpoint(TRUNCATE) + dispose, WAL file should be empty or absent."""
    db_path = tmp_path / "wal_test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    eng = create_async_engine(
        url,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng.sync_engine, "connect")
    def _set_pragmas(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    # Create a table and write some data to generate WAL entries
    async with eng.begin() as conn:
        await conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY)"))
    async with eng.begin() as conn:
        await conn.execute(text("INSERT INTO t VALUES (1)"))

    # Checkpoint and dispose (same pattern as close_db)
    async with eng.begin() as conn:
        await conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
    await eng.dispose()

    wal_path = db_path.parent / (db_path.name + "-wal")
    if wal_path.exists():
        assert wal_path.stat().st_size == 0


async def test_event_listener_fires_once_with_static_pool(tmp_path):
    """With StaticPool, the connect event listener should fire exactly once."""
    db_path = tmp_path / "fire_count.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    fire_count = 0

    eng = create_async_engine(
        url,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng.sync_engine, "connect")
    def _count_fires(dbapi_conn, connection_record):
        nonlocal fire_count
        fire_count += 1

    # Open multiple sessions
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    for _ in range(5):
        async with factory() as session:
            await session.execute(text("SELECT 1"))

    assert fire_count == 1
    await eng.dispose()


# ── Sales database PRAGMA tests ──────────────────────────────────


async def test_telegram_sales_db_pragmas(tmp_path):
    """Telegram SalesDatabase.init() must set WAL, FK, busy_timeout, synchronous."""
    from telegram_bot.sales.database import SalesDatabase

    db_path = str(tmp_path / "tg_sales_test.db")
    db = SalesDatabase(db_path)
    await db.init()

    cursor = await db._db.execute("PRAGMA journal_mode")
    journal = (await cursor.fetchone())[0]
    cursor = await db._db.execute("PRAGMA foreign_keys")
    fk = (await cursor.fetchone())[0]
    cursor = await db._db.execute("PRAGMA busy_timeout")
    busy = (await cursor.fetchone())[0]
    cursor = await db._db.execute("PRAGMA synchronous")
    sync = (await cursor.fetchone())[0]

    assert journal == "wal"
    assert fk == 1
    assert busy == 5000
    assert sync == 1  # NORMAL

    await db.close()


async def test_whatsapp_sales_db_pragmas(tmp_path):
    """WhatsApp SalesDatabase.init() must set WAL, FK, busy_timeout, synchronous."""
    from whatsapp_bot.sales.database import SalesDatabase

    db_path = str(tmp_path / "wa_sales_test.db")
    db = SalesDatabase(db_path)
    await db.init()

    cursor = await db._db.execute("PRAGMA journal_mode")
    journal = (await cursor.fetchone())[0]
    cursor = await db._db.execute("PRAGMA foreign_keys")
    fk = (await cursor.fetchone())[0]
    cursor = await db._db.execute("PRAGMA busy_timeout")
    busy = (await cursor.fetchone())[0]
    cursor = await db._db.execute("PRAGMA synchronous")
    sync = (await cursor.fetchone())[0]

    assert journal == "wal"
    assert fk == 1
    assert busy == 5000
    assert sync == 1  # NORMAL

    await db.close()


async def test_sales_db_fk_enforced(tmp_path):
    """Sales DB with FK=ON must reject invalid foreign key references."""
    from telegram_bot.sales.database import SalesDatabase

    db_path = str(tmp_path / "fk_test.db")
    db = SalesDatabase(db_path)
    await db.init()

    # events.user_id references users.user_id — inserting non-existent user must fail
    import aiosqlite

    with pytest.raises(aiosqlite.IntegrityError):
        await db._db.execute("INSERT INTO events (user_id, event_type) VALUES (999999, 'test')")
        await db._db.commit()

    await db.close()
