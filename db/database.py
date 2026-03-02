"""
SQLite database connection and session management.
Uses async SQLAlchemy with aiosqlite driver.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool


logger = logging.getLogger(__name__)

# Database path
DB_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DB_DIR / "secretary.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL query logging
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,  # Use StaticPool for SQLite
)


# Set SQLite PRAGMAs on every new physical connection.
# With StaticPool this fires exactly once (single persistent connection).
@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def init_db() -> None:
    """
    Initialize database: create tables if they don't exist.
    Call this on application startup.
    """
    from db.models import Base

    # Ensure data directory exists
    DB_DIR.mkdir(parents=True, exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info(f"📦 Database initialized at {DB_PATH}")


async def close_db() -> None:
    """
    Close database connections.
    Call this on application shutdown.
    """
    try:
        async with engine.begin() as conn:
            await conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
    except Exception as e:
        logger.warning("WAL checkpoint before close failed: %s", e)
    await engine.dispose()
    logger.info("📦 Database connections closed")


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI endpoints.
    Usage: session: AsyncSession = Depends(get_async_session)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for getting a database session.
    Usage: async with get_session_context() as session:
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db_status() -> dict:
    """
    Get database connection status for health checks.
    """
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            journal_mode = (await session.execute(text("PRAGMA journal_mode"))).scalar()
            fk_enabled = (await session.execute(text("PRAGMA foreign_keys"))).scalar()

        db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
        return {
            "status": "ok",
            "path": str(DB_PATH),
            "size_bytes": db_size,
            "size_mb": round(db_size / (1024 * 1024), 2),
            "journal_mode": journal_mode,
            "foreign_keys_enabled": bool(fk_enabled),
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "error",
            "error": str(e),
        }
