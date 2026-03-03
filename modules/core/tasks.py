"""Background task registry with lifecycle management."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable


logger = logging.getLogger(__name__)


@dataclass
class TaskInfo:
    """Runtime information about a registered task."""

    name: str
    status: str = "pending"  # pending | running | completed | failed | cancelled
    last_run: float | None = None
    run_count: int = 0
    last_error: str | None = None
    periodic: bool = False


@dataclass
class _TaskEntry:
    """Internal task registration entry."""

    name: str
    coro_fn: Callable[[], Awaitable[None]]
    interval: int | None = None
    initial_delay: int = 0
    info: TaskInfo = field(default=None)  # type: ignore[assignment]
    asyncio_task: asyncio.Task[None] | None = None

    def __post_init__(self) -> None:
        if self.info is None:
            self.info = TaskInfo(name=self.name, periodic=self.interval is not None)


class TaskRegistry:
    """Registry for named background tasks with start/cancel lifecycle.

    Supports periodic tasks (run on interval) and one-shot tasks (run once).
    All tasks are cancellable via cancel_all() for graceful shutdown.
    """

    def __init__(self) -> None:
        self._entries: dict[str, _TaskEntry] = {}

    def register(
        self,
        name: str,
        coro_fn: Callable[[], Awaitable[None]],
        *,
        interval: int | None = None,
        initial_delay: int = 0,
    ) -> None:
        """Register a background task.

        Args:
            name: Unique task name.
            coro_fn: Async callable to run.
            interval: Seconds between runs. None = one-shot task.
            initial_delay: Seconds to wait before first run.
        """
        if name in self._entries:
            raise ValueError(f"Task '{name}' is already registered")
        self._entries[name] = _TaskEntry(
            name=name,
            coro_fn=coro_fn,
            interval=interval,
            initial_delay=initial_delay,
        )

    async def start_all(self) -> None:
        """Create asyncio.Task for each registered task."""
        for entry in self._entries.values():
            if entry.asyncio_task is not None:
                continue
            entry.asyncio_task = asyncio.create_task(
                self._run_task(entry),
                name=f"task-registry:{entry.name}",
            )

    async def cancel_all(self, timeout: float = 10.0) -> None:
        """Cancel all running tasks and wait for them to finish.

        Args:
            timeout: Maximum seconds to wait for tasks to finish.
        """
        tasks = [
            entry.asyncio_task
            for entry in self._entries.values()
            if entry.asyncio_task is not None and not entry.asyncio_task.done()
        ]

        if not tasks:
            return

        for task in tasks:
            task.cancel()

        _done, pending = await asyncio.wait(tasks, timeout=timeout)

        for task in pending:
            logger.warning(
                "Task %s did not finish within %.1fs timeout",
                task.get_name(),
                timeout,
            )

    def list_tasks(self) -> list[TaskInfo]:
        """Return info about all registered tasks."""
        return [entry.info for entry in self._entries.values()]

    async def _run_task(self, entry: _TaskEntry) -> None:
        """Internal wrapper that runs a task with error handling."""
        info = entry.info
        try:
            if entry.initial_delay > 0:
                await asyncio.sleep(entry.initial_delay)

            while True:
                info.status = "running"
                try:
                    await entry.coro_fn()
                    info.last_run = time.time()
                    info.run_count += 1
                    info.last_error = None

                    if entry.interval is None:
                        info.status = "completed"
                        return

                except Exception as exc:
                    info.last_error = str(exc)
                    logger.error(
                        "Task '%s' failed: %s",
                        entry.name,
                        exc,
                        exc_info=True,
                    )
                    if entry.interval is None:
                        info.status = "failed"
                        return

                info.status = "running"
                await asyncio.sleep(entry.interval)  # type: ignore[arg-type]

        except asyncio.CancelledError:
            info.status = "cancelled"
            raise
