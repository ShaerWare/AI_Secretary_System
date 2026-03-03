"""In-process event bus for decoupled module communication."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypeVar


logger = logging.getLogger(__name__)

E = TypeVar("E", bound="BaseEvent")


@dataclass
class BaseEvent:
    """Base class for all events. Subclass with domain-specific fields."""

    timestamp: float = field(default_factory=time.time)


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
