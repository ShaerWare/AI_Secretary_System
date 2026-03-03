"""Modular health check registry."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


logger = logging.getLogger(__name__)

_STATUS_PRIORITY = {"ok": 0, "degraded": 1, "error": 2}


@dataclass
class HealthStatus:
    """Result of a single health check."""

    status: str  # "ok" | "degraded" | "error"
    details: dict[str, Any] = field(default_factory=dict)


class HealthRegistry:
    """Registry for modular health checks.

    Modules register named async health check functions.
    check_all() runs them in parallel with per-check timeout and
    returns aggregated status.
    """

    def __init__(self) -> None:
        self._checks: dict[str, Callable[[], Awaitable[HealthStatus]]] = {}

    def register(
        self,
        name: str,
        check: Callable[[], Awaitable[HealthStatus]],
    ) -> None:
        """Register a named health check.

        Args:
            name: Unique check name (e.g. "database", "redis").
            check: Async callable returning HealthStatus.
        """
        if name in self._checks:
            raise ValueError(f"Health check '{name}' is already registered")
        self._checks[name] = check

    async def check_all(self, timeout: float = 5.0) -> dict[str, Any]:
        """Run all registered checks in parallel.

        Each check has an individual timeout. Results are aggregated:
        all ok → ok, any degraded → degraded, any error → error.

        Returns:
            {"status": str, "checks": {name: {"status": ..., "details": ...}}}
        """
        if not self._checks:
            return {"status": "ok", "checks": {}}

        names = list(self._checks.keys())
        coros = [self._run_check(name, fn, timeout) for name, fn in self._checks.items()]
        results: list[HealthStatus] = await asyncio.gather(*coros)

        checks = {}
        worst = "ok"

        for name, result in zip(names, results, strict=True):
            checks[name] = {"status": result.status, "details": result.details}
            if _STATUS_PRIORITY.get(result.status, 2) > _STATUS_PRIORITY.get(worst, 0):
                worst = result.status

        return {"status": worst, "checks": checks}

    @staticmethod
    async def _run_check(
        name: str,
        check: Callable[[], Awaitable[HealthStatus]],
        timeout: float,
    ) -> HealthStatus:
        """Run a single health check with timeout and error handling."""
        try:
            return await asyncio.wait_for(check(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Health check '%s' timed out after %.1fs", name, timeout)
            return HealthStatus(status="error", details={"error": f"Timeout after {timeout}s"})
        except Exception as exc:
            logger.error("Health check '%s' failed: %s", name, exc, exc_info=True)
            return HealthStatus(status="error", details={"error": str(exc)})
