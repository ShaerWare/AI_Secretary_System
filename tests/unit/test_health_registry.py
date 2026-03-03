"""Tests for modules.core.health — HealthRegistry."""

import asyncio

import pytest

from modules.core.health import HealthRegistry, HealthStatus


async def test_single_check_ok():
    registry = HealthRegistry()

    async def ok_check():
        return HealthStatus(status="ok", details={"version": "1.0"})

    registry.register("service", ok_check)
    result = await registry.check_all()

    assert result["status"] == "ok"
    assert result["checks"]["service"]["status"] == "ok"
    assert result["checks"]["service"]["details"]["version"] == "1.0"


async def test_all_ok_aggregates_ok():
    registry = HealthRegistry()

    async def ok_a():
        return HealthStatus(status="ok")

    async def ok_b():
        return HealthStatus(status="ok")

    registry.register("a", ok_a)
    registry.register("b", ok_b)

    result = await registry.check_all()
    assert result["status"] == "ok"


async def test_degraded_aggregation():
    registry = HealthRegistry()

    async def ok_check():
        return HealthStatus(status="ok")

    async def degraded_check():
        return HealthStatus(status="degraded", details={"reason": "slow"})

    registry.register("ok", ok_check)
    registry.register("degraded", degraded_check)

    result = await registry.check_all()
    assert result["status"] == "degraded"


async def test_error_aggregation():
    registry = HealthRegistry()

    async def ok_check():
        return HealthStatus(status="ok")

    async def error_check():
        return HealthStatus(status="error", details={"reason": "down"})

    registry.register("ok", ok_check)
    registry.register("error", error_check)

    result = await registry.check_all()
    assert result["status"] == "error"


async def test_timeout_produces_error():
    registry = HealthRegistry()

    async def slow_check():
        await asyncio.sleep(10)
        return HealthStatus(status="ok")

    registry.register("slow", slow_check)
    result = await registry.check_all(timeout=0.05)

    assert result["status"] == "error"
    assert "Timeout" in result["checks"]["slow"]["details"]["error"]


async def test_exception_produces_error():
    registry = HealthRegistry()

    async def broken_check():
        raise RuntimeError("connection refused")

    registry.register("broken", broken_check)
    result = await registry.check_all()

    assert result["status"] == "error"
    assert "connection refused" in result["checks"]["broken"]["details"]["error"]


async def test_empty_registry():
    registry = HealthRegistry()
    result = await registry.check_all()

    assert result["status"] == "ok"
    assert result["checks"] == {}


async def test_duplicate_name_raises():
    registry = HealthRegistry()

    async def check():
        return HealthStatus(status="ok")

    registry.register("dup", check)

    with pytest.raises(ValueError, match="already registered"):
        registry.register("dup", check)
