"""Tests for db.retry — SQLITE_BUSY retry decorator."""

import sqlite3

import pytest
from sqlalchemy.exc import OperationalError

from db.retry import get_busy_retry_count, retry_on_busy


def _make_busy_error() -> OperationalError:
    """Create a realistic SQLAlchemy-wrapped 'database is locked' error."""
    orig = sqlite3.OperationalError("database is locked")
    return OperationalError("(sqlite3.OperationalError) database is locked", {}, orig)


def _make_other_error() -> OperationalError:
    """Create a non-BUSY OperationalError."""
    orig = sqlite3.OperationalError("no such table: foo")
    return OperationalError("(sqlite3.OperationalError) no such table: foo", {}, orig)


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_succeeds_on_first_try():
    """No retry when no error."""

    @retry_on_busy()
    async def ok():
        return 42

    assert await ok() == 42


@pytest.mark.asyncio
async def test_retries_on_locked():
    """Fails 2× then succeeds; counter increments by 2."""
    before = get_busy_retry_count()
    call_count = 0

    @retry_on_busy(base_delay=0.0)
    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise _make_busy_error()
        return "ok"

    result = await flaky()
    assert result == "ok"
    assert call_count == 3
    assert get_busy_retry_count() - before == 2


@pytest.mark.asyncio
async def test_exhausted_reraises():
    """All retries fail → original exception re-raised."""

    @retry_on_busy(max_retries=2, base_delay=0.0)
    async def always_locked():
        raise _make_busy_error()

    with pytest.raises(OperationalError, match="database is locked"):
        await always_locked()


@pytest.mark.asyncio
async def test_non_busy_error_not_retried():
    """Other OperationalError propagates immediately (call_count=1)."""
    call_count = 0

    @retry_on_busy(base_delay=0.0)
    async def bad_table():
        nonlocal call_count
        call_count += 1
        raise _make_other_error()

    with pytest.raises(OperationalError, match="no such table"):
        await bad_table()

    assert call_count == 1


@pytest.mark.asyncio
async def test_get_busy_retry_count():
    """Counter getter returns an int."""
    count = get_busy_retry_count()
    assert isinstance(count, int)
    assert count >= 0


@pytest.mark.asyncio
async def test_void_return():
    """Decorator works with None-returning functions."""

    @retry_on_busy()
    async def void_fn():
        pass

    result = await void_fn()
    assert result is None


@pytest.mark.asyncio
async def test_passes_args_and_kwargs():
    """Arguments forwarded correctly."""
    received = {}

    @retry_on_busy()
    async def capture(a, b, *, key="default"):
        received["a"] = a
        received["b"] = b
        received["key"] = key
        return a + b

    result = await capture(1, 2, key="custom")
    assert result == 3
    assert received == {"a": 1, "b": 2, "key": "custom"}
