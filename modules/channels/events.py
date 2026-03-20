"""Channel-level domain events (shared across telegram, whatsapp, etc.)."""

from dataclasses import dataclass

from modules.core.events import BaseEvent


@dataclass
class BotProcessDied(BaseEvent):
    """Emitted when a bot subprocess is detected as terminated.

    The bot-process-watcher periodic task publishes this event.
    Subscribers: audit logging, auto-restart with backoff.
    """

    channel: str = ""  # "telegram" | "whatsapp"
    instance_id: str = ""
    exit_code: int | None = None
    uptime_seconds: float = 0.0
