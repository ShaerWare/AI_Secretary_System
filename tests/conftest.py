"""Shared test fixtures for AI Secretary System tests."""

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def tmp_db_path(tmp_path):
    """Return a temporary SQLite database file path."""
    return tmp_path / "test.db"


@pytest_asyncio.fixture()
async def test_engine(tmp_db_path):
    """Create an async SQLAlchemy engine with PRAGMA event listener (same pattern as db/database.py)."""
    url = f"sqlite+aiosqlite:///{tmp_db_path}"
    eng = create_async_engine(
        url,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    yield eng
    await eng.dispose()


@pytest_asyncio.fixture()
async def test_session_factory(test_engine):
    """Create a session factory bound to the test engine."""
    return async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
