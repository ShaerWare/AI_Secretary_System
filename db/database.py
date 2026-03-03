"""
SQLite database connection and session management.
Uses async SQLAlchemy with aiosqlite driver.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Base class for all models"""

    pass


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
    import db.models  # noqa: F401 — ensure all models are registered on Base.metadata

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
            await session.commit()
        except Exception:
            await session.rollback()
            raise


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


async def _collect_db_status() -> dict:
    """Inner health check logic (separated for timeout wrapper)."""
    from db.retry import get_busy_retry_count

    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))
        journal_mode = (await session.execute(text("PRAGMA journal_mode"))).scalar()
        fk_enabled = (await session.execute(text("PRAGMA foreign_keys"))).scalar()
        busy_timeout = (await session.execute(text("PRAGMA busy_timeout"))).scalar()
        integrity = (await session.execute(text("PRAGMA integrity_check(1)"))).scalar()

    db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    wal_path = DB_PATH.with_suffix(".db-wal")
    wal_size = wal_path.stat().st_size if wal_path.exists() else 0

    return {
        "status": "ok",
        "path": str(DB_PATH),
        "size_bytes": db_size,
        "size_mb": round(db_size / (1024 * 1024), 2),
        "wal_size_bytes": wal_size,
        "integrity": integrity == "ok",
        "pragma": {
            "journal_mode": journal_mode,
            "foreign_keys": bool(fk_enabled),
            "busy_timeout": busy_timeout,
        },
        "busy_retry_count": get_busy_retry_count(),
    }


async def get_db_status() -> dict:
    """Get database connection status for health checks (5 s timeout)."""
    try:
        return await asyncio.wait_for(_collect_db_status(), timeout=5.0)
    except asyncio.TimeoutError:
        logger.error("Database health check timed out (5s)")
        from db.retry import get_busy_retry_count

        return {"status": "timeout", "busy_retry_count": get_busy_retry_count()}
    except Exception as e:
        logger.error("Database health check failed: %s", e)
        from db.retry import get_busy_retry_count

        return {"status": "error", "error": str(e), "busy_retry_count": get_busy_retry_count()}


async def run_vacuum() -> None:
    """Run VACUUM to reclaim disk space. Requires AUTOCOMMIT (no transaction)."""
    t0 = time.monotonic()
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text("VACUUM"))
    elapsed = time.monotonic() - t0
    logger.info("Database VACUUM completed in %.1fms", elapsed * 1000)
