"""Tests for modules.core.events — EventBus."""

from dataclasses import dataclass

from modules.core.events import BaseEvent, EventBus


@dataclass
class SampleEvent(BaseEvent):
    value: str = ""


@dataclass
class OtherEvent(BaseEvent):
    count: int = 0


async def test_subscribe_and_publish():
    bus = EventBus()
    received = []

    async def handler(event: SampleEvent):
        received.append(event.value)

    bus.subscribe(SampleEvent, handler)
    await bus.publish(SampleEvent(value="hello"))

    assert received == ["hello"]


async def test_multiple_handlers():
    bus = EventBus()
    results = []

    async def handler_a(event: SampleEvent):
        results.append("a")

    async def handler_b(event: SampleEvent):
        results.append("b")

    bus.subscribe(SampleEvent, handler_a)
    bus.subscribe(SampleEvent, handler_b)
    await bus.publish(SampleEvent(value="test"))

    assert sorted(results) == ["a", "b"]


async def test_handler_exception_does_not_propagate():
    bus = EventBus()
    received = []

    async def bad_handler(event: SampleEvent):
        raise RuntimeError("boom")

    async def good_handler(event: SampleEvent):
        received.append(event.value)

    bus.subscribe(SampleEvent, bad_handler)
    bus.subscribe(SampleEvent, good_handler)

    # Should not raise
    await bus.publish(SampleEvent(value="ok"))

    assert received == ["ok"]


async def test_publish_no_subscribers():
    bus = EventBus()
    # Should not raise
    await bus.publish(SampleEvent(value="ignored"))


async def test_event_type_filtering():
    bus = EventBus()
    sample_received = []
    other_received = []

    async def sample_handler(event: SampleEvent):
        sample_received.append(event.value)

    async def other_handler(event: OtherEvent):
        other_received.append(event.count)

    bus.subscribe(SampleEvent, sample_handler)
    bus.subscribe(OtherEvent, other_handler)

    await bus.publish(SampleEvent(value="s"))
    await bus.publish(OtherEvent(count=42))

    assert sample_received == ["s"]
    assert other_received == [42]


async def test_event_has_timestamp():
    event = SampleEvent(value="test")
    assert event.timestamp > 0


async def test_clear_removes_all_handlers():
    bus = EventBus()
    received = []

    async def handler(event: SampleEvent):
        received.append(event.value)

    bus.subscribe(SampleEvent, handler)
    bus.clear()
    await bus.publish(SampleEvent(value="after-clear"))

    assert received == []


async def test_multiple_publishes():
    bus = EventBus()
    received = []

    async def handler(event: SampleEvent):
        received.append(event.value)

    bus.subscribe(SampleEvent, handler)
    await bus.publish(SampleEvent(value="first"))
    await bus.publish(SampleEvent(value="second"))

    assert received == ["first", "second"]
