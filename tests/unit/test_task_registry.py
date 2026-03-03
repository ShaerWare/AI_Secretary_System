"""Tests for modules.core.tasks — TaskRegistry."""

import asyncio

import pytest

from modules.core.tasks import TaskRegistry


async def test_one_shot_task_runs():
    registry = TaskRegistry()
    ran = []

    async def job():
        ran.append(True)

    registry.register("job", job)
    await registry.start_all()

    # Give the task time to run
    await asyncio.sleep(0.05)

    assert ran == [True]
    info = registry.list_tasks()
    assert len(info) == 1
    assert info[0].status == "completed"
    assert info[0].run_count == 1

    await registry.cancel_all()


async def test_periodic_task_runs_multiple_times():
    registry = TaskRegistry()
    counter = []

    async def job():
        counter.append(1)

    registry.register("counter", job, interval=0)
    await registry.start_all()

    await asyncio.sleep(0.1)
    await registry.cancel_all()

    assert len(counter) >= 2


async def test_initial_delay():
    registry = TaskRegistry()
    ran = []

    async def job():
        ran.append(True)

    registry.register("delayed", job, initial_delay=100)
    await registry.start_all()

    await asyncio.sleep(0.05)
    assert ran == []

    await registry.cancel_all()


async def test_cancel_all_stops_tasks():
    registry = TaskRegistry()
    counter = []

    async def job():
        counter.append(1)

    registry.register("loop", job, interval=0)
    await registry.start_all()

    await asyncio.sleep(0.05)
    await registry.cancel_all()

    count_after_cancel = len(counter)
    await asyncio.sleep(0.05)

    assert len(counter) == count_after_cancel


async def test_task_exception_is_caught():
    registry = TaskRegistry()

    async def failing_job():
        raise RuntimeError("task error")

    registry.register("fail", failing_job)
    await registry.start_all()

    await asyncio.sleep(0.05)

    info = registry.list_tasks()
    assert info[0].status == "failed"
    assert info[0].last_error == "task error"

    await registry.cancel_all()


async def test_periodic_task_continues_after_error():
    registry = TaskRegistry()
    counter = []

    async def flaky_job():
        counter.append(1)
        if len(counter) == 1:
            raise RuntimeError("first run fails")

    registry.register("flaky", flaky_job, interval=0)
    await registry.start_all()

    await asyncio.sleep(0.1)
    await registry.cancel_all()

    # Should have continued running after the first failure
    assert len(counter) >= 2


async def test_duplicate_name_raises():
    registry = TaskRegistry()

    async def job():
        pass

    registry.register("dup", job)

    with pytest.raises(ValueError, match="already registered"):
        registry.register("dup", job)


async def test_list_tasks():
    registry = TaskRegistry()

    async def job():
        pass

    registry.register("a", job)
    registry.register("b", job, interval=60)

    tasks = registry.list_tasks()
    assert len(tasks) == 2

    names = {t.name for t in tasks}
    assert names == {"a", "b"}

    periodic = {t.name: t.periodic for t in tasks}
    assert periodic == {"a": False, "b": True}
