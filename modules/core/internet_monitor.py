"""Internet connectivity monitor with LLM backend auto-switching.

Periodically checks internet connectivity and switches between:
- Online: Claude bridge / cloud LLM provider
- Offline: local vLLM (Qwen)

Uses EventBus to notify other services (GSM voice calls, SMS) about changes.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

import httpx

from modules.core.events import BaseEvent


if TYPE_CHECKING:
    from modules.core.events import EventBus

logger = logging.getLogger(__name__)


class ConnectivityStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"  # internet works but LLM provider unreachable


@dataclass
class InternetStatusChanged(BaseEvent):
    """Emitted when internet connectivity status changes."""

    status: ConnectivityStatus = ConnectivityStatus.OFFLINE
    previous_status: ConnectivityStatus = ConnectivityStatus.OFFLINE
    llm_backend: str = ""  # current active backend after switch


@dataclass
class InternetMonitorState:
    """Observable state of the internet monitor."""

    status: ConnectivityStatus = ConnectivityStatus.OFFLINE
    last_check: float = 0
    last_online: float = 0
    last_offline: float = 0
    check_count: int = 0
    switch_count: int = 0
    current_llm_backend: str = ""
    ping_ms: float | None = None


class InternetMonitor:
    """Monitors internet connectivity and switches LLM backend accordingly.

    Args:
        event_bus: EventBus for publishing InternetStatusChanged events.
        check_interval: Seconds between connectivity checks.
        ping_targets: URLs to check for internet connectivity.
        cloud_health_url: URL to check cloud LLM provider health.
        offline_threshold: Consecutive failures before declaring offline.
        online_threshold: Consecutive successes before declaring online.
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        *,
        check_interval: int = 30,
        ping_targets: list[str] | None = None,
        cloud_health_url: str | None = None,
        offline_threshold: int = 2,
        online_threshold: int = 1,
    ) -> None:
        self.event_bus = event_bus
        self.check_interval = check_interval
        self.ping_targets = ping_targets or [
            "https://dns.google/resolve?name=example.com",
            "https://1.1.1.1/cdn-cgi/trace",
        ]
        self.cloud_health_url = cloud_health_url
        self.offline_threshold = offline_threshold
        self.online_threshold = online_threshold

        self.state = InternetMonitorState()

        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._switch_callback: Any = None  # set by set_switch_callback()
        self._running = False
        self._task: asyncio.Task[None] | None = None

    def set_switch_callback(
        self,
        callback: Any,
    ) -> None:
        """Set callback for LLM switching: callback(status) -> new_backend_name.

        The callback receives ConnectivityStatus and should switch the
        container.llm_service accordingly. Returns the name of the new backend.
        """
        self._switch_callback = callback

    async def start(self) -> None:
        """Start periodic connectivity checking."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(
            self._check_loop(),
            name="internet-monitor",
        )
        logger.info(
            "InternetMonitor started (interval=%ds, targets=%s)",
            self.check_interval,
            self.ping_targets,
        )

    async def stop(self) -> None:
        """Stop the monitor."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("InternetMonitor stopped")

    async def check_now(self) -> ConnectivityStatus:
        """Run a single connectivity check immediately."""
        return await self._do_check()

    async def _check_loop(self) -> None:
        """Main loop: check connectivity periodically."""
        # Initial check immediately
        await self._do_check()

        while self._running:
            try:
                await asyncio.sleep(self.check_interval)
                await self._do_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("InternetMonitor error: %s", e)
                await asyncio.sleep(5)

    async def _do_check(self) -> ConnectivityStatus:
        """Perform connectivity check and handle state transitions."""
        self.state.check_count += 1
        self.state.last_check = time.time()

        internet_ok = await self._ping_internet()

        if internet_ok:
            # Check cloud LLM provider specifically
            cloud_ok = await self._check_cloud_llm() if self.cloud_health_url else True
            new_status = ConnectivityStatus.ONLINE if cloud_ok else ConnectivityStatus.DEGRADED

            self._consecutive_successes += 1
            self._consecutive_failures = 0

            if self._consecutive_successes >= self.online_threshold:
                await self._transition_to(new_status)
        else:
            self._consecutive_failures += 1
            self._consecutive_successes = 0

            if self._consecutive_failures >= self.offline_threshold:
                await self._transition_to(ConnectivityStatus.OFFLINE)

        return self.state.status

    async def _ping_internet(self) -> bool:
        """Check basic internet connectivity."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            for url in self.ping_targets:
                try:
                    start = time.time()
                    resp = await client.get(url)
                    self.state.ping_ms = (time.time() - start) * 1000
                    if resp.status_code < 500:
                        return True
                except Exception:
                    continue
        self.state.ping_ms = None
        return False

    async def _check_cloud_llm(self) -> bool:
        """Check if cloud LLM provider is reachable."""
        if not self.cloud_health_url:
            return True
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self.cloud_health_url)
                return resp.status_code < 500
        except Exception:
            return False

    async def _transition_to(self, new_status: ConnectivityStatus) -> None:
        """Handle status transition and trigger LLM switch if needed."""
        old_status = self.state.status

        if old_status == new_status:
            # Update timestamps even if status didn't change
            if new_status == ConnectivityStatus.ONLINE:
                self.state.last_online = time.time()
            else:
                self.state.last_offline = time.time()
            return

        # Status changed
        self.state.status = new_status
        self.state.switch_count += 1

        if new_status in (ConnectivityStatus.ONLINE, ConnectivityStatus.DEGRADED):
            self.state.last_online = time.time()
        else:
            self.state.last_offline = time.time()

        logger.warning(
            "Internet status: %s -> %s (switches: %d)",
            old_status.value,
            new_status.value,
            self.state.switch_count,
        )

        # Switch LLM backend
        new_backend = ""
        if self._switch_callback:
            try:
                new_backend = await self._switch_callback(new_status)
                self.state.current_llm_backend = new_backend
                logger.info("LLM backend switched to: %s", new_backend)
            except Exception as e:
                logger.error("LLM switch failed: %s", e)

        # Publish event
        if self.event_bus:
            await self.event_bus.publish(
                InternetStatusChanged(
                    status=new_status,
                    previous_status=old_status,
                    llm_backend=new_backend,
                )
            )
