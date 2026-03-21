"""In-process event bus for decoupled module communication."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, TypeVar


logger = logging.getLogger(__name__)

E = TypeVar("E", bound="BaseEvent")


@dataclass
class BaseEvent:
    """Base class for all events. Subclass with domain-specific fields."""

    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Domain events
# ---------------------------------------------------------------------------


class ConnectivityStatus(str, Enum):
    """Internet connectivity status for InternetMonitor."""

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
class UserRoleChanged(BaseEvent):
    """Emitted when a user's role is changed (workspace or legacy)."""

    user_id: int = 0
    workspace_id: int = 0
    old_role: str = ""
    new_role: str = ""


@dataclass
class SessionRevoked(BaseEvent):
    """Emitted when all sessions for a user should be revoked."""

    user_id: int = 0
    reason: str = ""  # "password_changed", "deactivated", "member_removed"


@dataclass
class DatasetSynced(BaseEvent):
    """Emitted after CRM/ecommerce/kanban sync writes files to disk.

    Knowledge domain subscribes to create/update DB records and reload RAG index.
    """

    source: str = ""  # "amocrm" | "woocommerce" | "kanban"
    collection_slug: str = ""
    action: str = ""  # "synced" | "cleared"
    # Collection metadata (used for auto-creation on first sync)
    collection_name: str = ""
    collection_description: str = ""
    base_dir: str = ""
    # Document list for "synced" action: [{filename, title, source_type, file_size_bytes, section_count}]
    documents: list = field(default_factory=list)
    # Whether to delete the collection record on "cleared" (kanban does this)
    delete_collection: bool = False


@dataclass
class ConfigChanged(BaseEvent):
    """Emitted when a global config key is updated via ConfigService.

    Subscribers should filter by *namespace* (derived from the key,
    e.g. ``"widget"``, ``"telegram"``, ``"tts"``) and ignore irrelevant
    changes.  Handlers must be idempotent.
    """

    key: str = ""
    value: Any = None
    previous_value: Any = None
    namespace: str = ""  # first segment of dotted key, or key itself


class EventBus:
    """Simple in-process pub/sub for async event handlers.

    Handlers are async callables executed concurrently via asyncio.gather.
    Exceptions in handlers are logged but never propagated to the publisher.
    """

    def __init__(self) -> None:
        self._handlers: dict[type[BaseEvent], list[Callable[..., Awaitable[None]]]] = defaultdict(
            list
        )

    def subscribe(
        self,
        event_type: type[E],
        handler: Callable[[E], Awaitable[None]],
    ) -> None:
        """Register a handler for a specific event type."""
        self._handlers[event_type].append(handler)

    async def publish(self, event: BaseEvent) -> None:
        """Publish an event to all subscribed handlers.

        All handlers run concurrently. Exceptions are logged, not propagated.
        Awaits completion of all handlers before returning.
        """
        handlers = self._handlers.get(type(event), [])
        if not handlers:
            return

        results: list[BaseException | Any] = await asyncio.gather(
            *(h(event) for h in handlers),
            return_exceptions=True,
        )

        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                handler = handlers[i]
                logger.error(
                    "Event handler %s.%s failed for %s: %s",
                    handler.__module__,
                    handler.__qualname__,
                    type(event).__name__,
                    result,
                    exc_info=result,
                )

    def clear(self) -> None:
        """Remove all handlers. Useful for testing."""
        self._handlers.clear()
