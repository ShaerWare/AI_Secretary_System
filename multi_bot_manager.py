#!/usr/bin/env python3
"""
Multi-Bot Manager for AI Secretary System.

Manages multiple Telegram bot instances as separate subprocesses.
Each bot runs independently with its own configuration loaded from the database.
"""

import asyncio
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


logger = logging.getLogger(__name__)


class BotProcess:
    """Represents a running bot process."""

    def __init__(self, instance_id: str, process: subprocess.Popen, log_file: Path):
        self.instance_id = instance_id
        self.process = process
        self.log_file = log_file
        self.started_at = datetime.utcnow()

    @property
    def is_running(self) -> bool:
        """Check if process is still running."""
        return self.process.poll() is None

    @property
    def pid(self) -> Optional[int]:
        """Get process ID."""
        return self.process.pid if self.is_running else None

    @property
    def uptime_seconds(self) -> int:
        """Get uptime in seconds."""
        return int((datetime.utcnow() - self.started_at).total_seconds())

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "instance_id": self.instance_id,
            "pid": self.pid,
            "is_running": self.is_running,
            "log_file": str(self.log_file),
            "started_at": self.started_at.isoformat(),
            "uptime_seconds": self.uptime_seconds,
        }


class MultiBotManager:
    """
    Manages multiple Telegram bot instances.

    Each bot is run as a separate subprocess with the BOT_INSTANCE_ID
    environment variable set to load its specific configuration.
    """

    def __init__(self):
        self._processes: Dict[str, BotProcess] = {}
        self._lock = asyncio.Lock()
        self._logs_dir = Path(__file__).parent / "logs"
        self._logs_dir.mkdir(exist_ok=True)
        # New aiogram bot module (replaces old telegram_bot_service.py)
        self._bot_module = "telegram_bot"
        self._bot_module_path = Path(__file__).parent / "telegram_bot"

    def _get_log_path(self, instance_id: str) -> Path:
        """Get log file path for bot instance."""
        return self._logs_dir / f"telegram_bot_{instance_id}.log"

    async def start_bot(self, instance_id: str) -> dict:
        """
        Start a bot instance.

        Args:
            instance_id: The bot instance ID to start

        Returns:
            Status dict with pid and info
        """
        async with self._lock:
            # Check if already running
            if instance_id in self._processes:
                proc = self._processes[instance_id]
                if proc.is_running:
                    return {
                        "status": "already_running",
                        "pid": proc.pid,
                        "instance_id": instance_id,
                    }
                else:
                    # Clean up dead process
                    del self._processes[instance_id]

            if not self._bot_module_path.exists():
                return {
                    "status": "error",
                    "error": f"Bot module not found: {self._bot_module_path}",
                    "instance_id": instance_id,
                }

            # Set up environment
            env = os.environ.copy()
            env["BOT_INSTANCE_ID"] = instance_id
            env["PYTHONUNBUFFERED"] = "1"

            # Set up log file
            log_file = self._get_log_path(instance_id)

            try:
                # Start subprocess
                with open(log_file, "a") as log_fd:
                    log_fd.write(f"\n{'=' * 60}\n")
                    log_fd.write(f"Starting bot instance: {instance_id}\n")
                    log_fd.write(f"Time: {datetime.utcnow().isoformat()}\n")
                    log_fd.write(f"{'=' * 60}\n\n")

                    # Run as module: python -m telegram_bot
                    process = subprocess.Popen(
                        [sys.executable, "-m", self._bot_module],
                        env=env,
                        stdout=log_fd,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,  # Don't kill on parent exit
                        cwd=str(Path(__file__).parent),  # Run from project root
                    )

                self._processes[instance_id] = BotProcess(
                    instance_id=instance_id,
                    process=process,
                    log_file=log_file,
                )

                logger.info(f"Started bot instance {instance_id} with PID {process.pid}")

                return {
                    "status": "started",
                    "pid": process.pid,
                    "instance_id": instance_id,
                    "log_file": str(log_file),
                }

            except Exception as e:
                logger.error(f"Failed to start bot {instance_id}: {e}")
                return {
                    "status": "error",
                    "error": str(e),
                    "instance_id": instance_id,
                }

    async def stop_bot(self, instance_id: str, timeout: int = 5) -> dict:
        """
        Stop a bot instance.

        Args:
            instance_id: The bot instance ID to stop
            timeout: Seconds to wait for graceful shutdown

        Returns:
            Status dict
        """
        async with self._lock:
            if instance_id not in self._processes:
                return {
                    "status": "not_running",
                    "instance_id": instance_id,
                }

            proc = self._processes[instance_id]

            if not proc.is_running:
                del self._processes[instance_id]
                return {
                    "status": "already_stopped",
                    "instance_id": instance_id,
                }

            try:
                # Try graceful shutdown first
                proc.process.terminate()
                try:
                    proc.process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    # Force kill
                    proc.process.kill()
                    proc.process.wait(timeout=2)

                del self._processes[instance_id]
                logger.info(f"Stopped bot instance {instance_id}")

                return {
                    "status": "stopped",
                    "instance_id": instance_id,
                }

            except Exception as e:
                logger.error(f"Error stopping bot {instance_id}: {e}")
                return {
                    "status": "error",
                    "error": str(e),
                    "instance_id": instance_id,
                }

    async def restart_bot(self, instance_id: str) -> dict:
        """Restart a bot instance."""
        await self.stop_bot(instance_id)
        await asyncio.sleep(0.5)  # Brief pause between stop and start
        return await self.start_bot(instance_id)

    async def get_bot_status(self, instance_id: str) -> dict:
        """Get status of a specific bot instance."""
        async with self._lock:
            if instance_id not in self._processes:
                return {
                    "status": "stopped",
                    "running": False,
                    "instance_id": instance_id,
                }

            proc = self._processes[instance_id]

            if not proc.is_running:
                # Clean up dead process
                del self._processes[instance_id]
                return {
                    "status": "stopped",
                    "running": False,
                    "instance_id": instance_id,
                }

            return {
                "status": "running",
                "running": True,
                "instance_id": instance_id,
                "pid": proc.pid,
                "log_file": str(proc.log_file),
                "started_at": proc.started_at.isoformat(),
                "uptime_seconds": proc.uptime_seconds,
            }

    async def get_all_statuses(self) -> Dict[str, dict]:
        """Get status of all bot instances."""
        async with self._lock:
            statuses = {}
            dead_instances = []

            for instance_id, proc in self._processes.items():
                if proc.is_running:
                    statuses[instance_id] = {
                        "running": True,
                        "pid": proc.pid,
                        "started_at": proc.started_at.isoformat(),
                        "uptime_seconds": proc.uptime_seconds,
                    }
                else:
                    statuses[instance_id] = {"running": False}
                    dead_instances.append(instance_id)

            # Clean up dead processes
            for instance_id in dead_instances:
                del self._processes[instance_id]

            return statuses

    async def get_running_instances(self) -> List[str]:
        """Get list of running instance IDs."""
        statuses = await self.get_all_statuses()
        return [k for k, v in statuses.items() if v.get("running")]

    async def stop_all(self) -> dict:
        """Stop all running bot instances."""
        results = {}
        instance_ids = list(self._processes.keys())

        for instance_id in instance_ids:
            results[instance_id] = await self.stop_bot(instance_id)

        return results

    def get_log_path(self, instance_id: str) -> Path:
        """Get log file path for bot instance."""
        return self._get_log_path(instance_id)

    async def get_recent_logs(self, instance_id: str, lines: int = 100) -> str:
        """Get recent log lines for a bot instance."""
        log_file = self._get_log_path(instance_id)
        if not log_file.exists():
            return ""

        try:
            # Read last N lines
            with open(log_file) as f:
                all_lines = f.readlines()
                return "".join(all_lines[-lines:])
        except Exception as e:
            logger.error(f"Error reading logs for {instance_id}: {e}")
            return f"Error reading logs: {e}"


# Global instance
multi_bot_manager = MultiBotManager()
