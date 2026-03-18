"""Health check utilities for CLI availability."""

import asyncio
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .subprocess import create_subprocess


logger = logging.getLogger(__name__)


@dataclass
class CLIStatus:
    """Status of a CLI tool."""

    name: str
    available: bool
    path: str | None = None
    version: str | None = None
    error: str | None = None
    last_checked: datetime = field(default_factory=datetime.now)


async def check_cli_available(
    cli_name: str,
    cli_path: str,
    version_flag: str = "--version",
) -> CLIStatus:
    """
    Check if a CLI tool is available and get its version.

    Args:
        cli_name: Human-readable name for the CLI
        cli_path: Path or command name for the CLI
        version_flag: Flag to get version info

    Returns:
        CLIStatus with availability info
    """
    # First check if an absolute path was provided
    if cli_path and Path(cli_path).is_absolute() and Path(cli_path).is_file():
        resolved_path = cli_path
    else:
        resolved_path = shutil.which(cli_path) if cli_path else None

    if not resolved_path:
        return CLIStatus(
            name=cli_name,
            available=False,
            path=None,
            error=f"Command '{cli_path}' not found in PATH",
        )

    # Try to get version
    try:
        process = await create_subprocess(
            [cli_path, version_flag],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, _stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=25,
        )

        if process.returncode == 0:
            version = stdout.decode().strip().split("\n")[0]
            return CLIStatus(
                name=cli_name,
                available=True,
                path=resolved_path,
                version=version,
            )
        else:
            # Some CLIs return non-zero for --version but still work
            return CLIStatus(
                name=cli_name,
                available=True,
                path=resolved_path,
                version="unknown",
            )

    except asyncio.TimeoutError:
        return CLIStatus(
            name=cli_name,
            available=False,
            path=resolved_path,
            error="Timeout getting version",
        )
    except Exception as e:
        return CLIStatus(
            name=cli_name,
            available=False,
            path=resolved_path,
            error=str(e),
        )


async def check_all_clis(settings) -> dict[str, CLIStatus]:
    """
    Check all configured CLI tools.

    Returns:
        Dict mapping provider name to CLIStatus
    """
    checks = await asyncio.gather(
        check_cli_available("Claude Code", settings.claude_cli_path, "-v"),
        check_cli_available("Gemini CLI", settings.gemini_cli_path, "-v"),
        check_cli_available("Shell-GPT", settings.gpt_cli_path, "--version"),
    )

    return {
        "claude": checks[0],
        "gemini": checks[1],
        "gpt": checks[2],
    }


def log_cli_status(statuses: dict[str, CLIStatus]) -> None:
    """Log CLI availability status."""
    for name, status in statuses.items():
        if status.available:
            logger.info(f"✓ {status.name}: available at {status.path} ({status.version})")
        else:
            logger.warning(f"✗ {status.name}: {status.error}")
