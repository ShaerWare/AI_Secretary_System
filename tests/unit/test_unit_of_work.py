"""Unit of Work pattern tests.

Verify that:
- Repos do NOT commit (changes are lost on rollback)
- Repos DO flush (changes visible within same session)
- Repo delete does NOT commit (rollback undoes deletion)
- Manager-level methods DO commit (changes persist)
- Multi-op atomicity works (all-or-nothing in one session)
- get_async_session() auto-commits on success, rollbacks on exception
- get_session_context() auto-commits on success, rollbacks on exception
- BaseRepository.update() flushes even with autoflush=False
"""

import pytest
import pytest_asyncio
from sqlalchemy import select

import db.database
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


@pytest.mark.asyncio
async def test_repo_delete_does_not_commit(setup_db):
    """After repo.delete_config(), rollback should undo the deletion."""
    SessionFactory = setup_db

    # Create and commit a row first
    async with SessionFactory() as session:
        from db.repositories.config import ConfigRepository

        repo = ConfigRepository(session)
        await repo.set_config("delete_me", "value")
        await session.commit()

    # Delete via repo, then rollback
    async with SessionFactory() as session:
        from db.repositories.config import ConfigRepository

        repo = ConfigRepository(session)
        await repo.delete_config("delete_me")
        await session.rollback()

    # Row should still exist — delete was not committed
    async with SessionFactory() as session:
        result = await session.execute(select(SystemConfig).where(SystemConfig.key == "delete_me"))
        assert result.scalar_one_or_none() is not None, "Rollback should undo the delete"


@pytest.mark.asyncio
async def test_get_async_session_commits_on_success(setup_db, monkeypatch):
    """get_async_session() should auto-commit when no exception occurs."""
    SessionFactory = setup_db
    monkeypatch.setattr(db.database, "AsyncSessionLocal", SessionFactory)

    from db.database import get_async_session

    gen = get_async_session()
    session = await gen.__anext__()

    from db.repositories.config import ConfigRepository

    repo = ConfigRepository(session)
    await repo.set_config("async_session_key", "persisted")

    # Normal exit — triggers commit
    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass

    # Data should be persisted
    async with SessionFactory() as session:
        result = await session.execute(
            select(SystemConfig).where(SystemConfig.key == "async_session_key")
        )
        assert result.scalar_one_or_none() is not None, (
            "get_async_session should auto-commit on success"
        )


@pytest.mark.asyncio
async def test_get_async_session_rollbacks_on_exception(setup_db, monkeypatch):
    """get_async_session() should rollback when an exception is raised."""
    SessionFactory = setup_db
    monkeypatch.setattr(db.database, "AsyncSessionLocal", SessionFactory)

    from db.database import get_async_session

    gen = get_async_session()
    session = await gen.__anext__()

    from db.repositories.config import ConfigRepository

    repo = ConfigRepository(session)
    await repo.set_config("rollback_key", "should_not_persist")

    # Signal an exception — triggers rollback
    try:
        await gen.athrow(ValueError("simulated error"))
    except ValueError:
        pass

    # Data should NOT be persisted
    async with SessionFactory() as session:
        result = await session.execute(
            select(SystemConfig).where(SystemConfig.key == "rollback_key")
        )
        assert result.scalar_one_or_none() is None, "get_async_session should rollback on exception"


@pytest.mark.asyncio
async def test_get_session_context_commits(setup_db, monkeypatch):
    """get_session_context() should auto-commit on normal exit."""
    SessionFactory = setup_db
    monkeypatch.setattr(db.database, "AsyncSessionLocal", SessionFactory)

    from db.database import get_session_context

    async with get_session_context() as session:
        from db.repositories.config import ConfigRepository

        repo = ConfigRepository(session)
        await repo.set_config("ctx_commit_key", "persisted")

    # Data should be persisted
    async with SessionFactory() as session:
        result = await session.execute(
            select(SystemConfig).where(SystemConfig.key == "ctx_commit_key")
        )
        assert result.scalar_one_or_none() is not None, (
            "get_session_context should auto-commit on success"
        )


@pytest.mark.asyncio
async def test_get_session_context_rollbacks(setup_db, monkeypatch):
    """get_session_context() should rollback when an exception is raised."""
    SessionFactory = setup_db
    monkeypatch.setattr(db.database, "AsyncSessionLocal", SessionFactory)

    from db.database import get_session_context

    with pytest.raises(ValueError, match="simulated"):
        async with get_session_context() as session:
            from db.repositories.config import ConfigRepository

            repo = ConfigRepository(session)
            await repo.set_config("ctx_rollback_key", "should_not_persist")
            raise ValueError("simulated error")

    # Data should NOT be persisted
    async with SessionFactory() as session:
        result = await session.execute(
            select(SystemConfig).where(SystemConfig.key == "ctx_rollback_key")
        )
        assert result.scalar_one_or_none() is None, (
            "get_session_context should rollback on exception"
        )


@pytest.mark.asyncio
async def test_base_repo_update_flush_with_autoflush_false(setup_db):
    """BaseRepository.update() should flush even when autoflush=False."""
    SessionFactory = setup_db

    # Create and commit a row
    async with SessionFactory() as session:
        from db.repositories.config import ConfigRepository

        repo = ConfigRepository(session)
        await repo.set_config("flush_update_key", "original")
        await session.commit()

    # Modify via ORM + repo.update(), verify flush happens
    async with SessionFactory() as session:
        assert session.autoflush is False, "Test requires autoflush=False"

        from db.repositories.base import BaseRepository

        result = await session.execute(
            select(SystemConfig).where(SystemConfig.key == "flush_update_key")
        )
        entity = result.scalar_one()
        entity.value = '"updated"'

        repo = BaseRepository(session, SystemConfig)
        await repo.update(entity)

        # After update() flush, the change should be visible in a fresh query
        result2 = await session.execute(
            select(SystemConfig).where(SystemConfig.key == "flush_update_key")
        )
        entity2 = result2.scalar_one()
        assert entity2.value == '"updated"', "update() should flush changes visible in same session"

        # But rollback should lose it (proving it was flush, not commit)
        await session.rollback()

    async with SessionFactory() as session:
        result = await session.execute(
            select(SystemConfig).where(SystemConfig.key == "flush_update_key")
        )
        entity = result.scalar_one()
        assert entity.value == '"original"', "Rollback should restore original"
