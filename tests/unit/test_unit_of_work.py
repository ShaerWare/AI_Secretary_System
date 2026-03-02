"""Unit of Work pattern tests.

Verify that:
- Repos do NOT commit (changes are lost on rollback)
- Repos DO flush (changes visible within same session)
- Manager-level methods DO commit (changes persist)
- Multi-op atomicity works (all-or-nothing in one session)
"""

import pytest
import pytest_asyncio
from sqlalchemy import select

from db.models import Base, SystemConfig


@pytest_asyncio.fixture()
async def setup_db(test_engine, test_session_factory):
    """Create tables in the test database."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return test_session_factory


@pytest.mark.asyncio
async def test_repo_does_not_commit(setup_db):
    """After repo.create(), rollback should lose the data."""
    SessionFactory = setup_db

    async with SessionFactory() as session:
        from db.repositories.config import ConfigRepository

        repo = ConfigRepository(session)
        await repo.set_config("test_key", "test_value")
        # Explicitly rollback — should lose everything
        await session.rollback()

    # Verify data is gone
    async with SessionFactory() as session:
        result = await session.execute(select(SystemConfig).where(SystemConfig.key == "test_key"))
        assert result.scalar_one_or_none() is None, "Rollback should have lost the data"


@pytest.mark.asyncio
async def test_repo_flush_visible_in_session(setup_db):
    """After repo operation, flush makes data visible within the same session."""
    SessionFactory = setup_db

    async with SessionFactory() as session:
        from db.repositories.config import ConfigRepository

        repo = ConfigRepository(session)
        await repo.set_config("flush_test", "visible")

        # Should be visible in the same session after flush
        result = await session.execute(select(SystemConfig).where(SystemConfig.key == "flush_test"))
        row = result.scalar_one_or_none()
        assert row is not None, "Flushed data should be visible in same session"
        assert row.value == '"visible"'  # ConfigRepository JSON-encodes values


@pytest.mark.asyncio
async def test_commit_persists_data(setup_db):
    """After commit, data survives session close."""
    SessionFactory = setup_db

    async with SessionFactory() as session:
        from db.repositories.config import ConfigRepository

        repo = ConfigRepository(session)
        await repo.set_config("persist_key", "persist_value")
        await session.commit()

    # Verify data persists in a new session
    async with SessionFactory() as session:
        result = await session.execute(
            select(SystemConfig).where(SystemConfig.key == "persist_key")
        )
        row = result.scalar_one_or_none()
        assert row is not None, "Committed data should persist"


@pytest.mark.asyncio
async def test_multi_op_atomicity(setup_db):
    """Multiple repo ops in one session: commit saves all, rollback loses all."""
    SessionFactory = setup_db

    # Test: commit saves all
    async with SessionFactory() as session:
        from db.repositories.config import ConfigRepository

        repo = ConfigRepository(session)
        await repo.set_config("atom_a", "val_a")
        await repo.set_config("atom_b", "val_b")
        await session.commit()

    async with SessionFactory() as session:
        result_a = await session.execute(select(SystemConfig).where(SystemConfig.key == "atom_a"))
        result_b = await session.execute(select(SystemConfig).where(SystemConfig.key == "atom_b"))
        assert result_a.scalar_one_or_none() is not None
        assert result_b.scalar_one_or_none() is not None

    # Test: rollback loses all
    async with SessionFactory() as session:
        from db.repositories.config import ConfigRepository

        repo = ConfigRepository(session)
        await repo.set_config("atom_c", "val_c")
        await repo.set_config("atom_d", "val_d")
        await session.rollback()

    async with SessionFactory() as session:
        result_c = await session.execute(select(SystemConfig).where(SystemConfig.key == "atom_c"))
        result_d = await session.execute(select(SystemConfig).where(SystemConfig.key == "atom_d"))
        assert result_c.scalar_one_or_none() is None, "Rollback should lose atom_c"
        assert result_d.scalar_one_or_none() is None, "Rollback should lose atom_d"
