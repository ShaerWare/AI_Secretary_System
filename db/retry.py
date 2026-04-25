"""
SQLITE_BUSY retry decorator — last-resort safety net.

SQLite WAL mode with busy_timeout=5000 handles most contention internally.
If the 5 s kernel-level wait is exhausted under extreme concurrency,
OperationalError("database is locked") bubbles up. This decorator retries
the entire manager method (which creates a fresh session/transaction).
"""

import asyncio
import functools
import logging
import sqlite3
from typing import Any, Callable, TypeVar

from sqlalchemy.exc import OperationalError


logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable)

_busy_retry_count: int = 0


def get_busy_retry_count() -> int:
    """Return cumulative number of SQLITE_BUSY retries (for health check)."""
    return _busy_retry_count


def _is_sqlite_busy(exc: BaseException) -> bool:
    """Check whether *exc* is a SQLAlchemy-wrapped sqlite3 'database is locked' error."""
    if not isinstance(exc, OperationalError):
        return False
    orig = getattr(exc, "orig", None)
    if not isinstance(orig, sqlite3.OperationalError):
        return False
    return "database is locked" in str(orig).lower()


def retry_on_busy(max_retries: int = 3, base_delay: float = 0.1) -> Callable[[F], F]:
    """Decorator: retry an async function on SQLITE_BUSY with exponential back-off.

    Parameters
    ----------
    max_retries:
        Maximum number of retries (not counting the first attempt).
    base_delay:
        Initial delay in seconds; doubles each retry (0.1 → 0.2 → 0.4).
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            global _busy_retry_count
            last_exc: BaseException | None = None
            for attempt in range(max_retries + 1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:
                    if not _is_sqlite_busy(exc):
                        raise
                    last_exc = exc
                    if attempt < max_retries:
                        delay = base_delay * (2**attempt)
                        _busy_retry_count += 1
                        logger.warning(
                            "SQLITE_BUSY on %s(), retry %d/%d in %.2fs",
                            fn.__qualname__,
                            attempt + 1,
                            max_retries,
                            delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "SQLITE_BUSY on %s(): all %d retries exhausted",
                            fn.__qualname__,
                            max_retries,
                        )
                        raise last_exc  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator
