"""Tests for the event framework."""

from __future__ import annotations

import asyncio
import uuid
from typing import ClassVar

import pytest
from shared_core.events import (
    BaseEvent,
    EventPublisher,
    EventRegistry,
    EventSubscriber,
    deserialize_event,
    serialize_event,
)
from shared_core.exceptions import NotFoundError
from shared_core.queue import QueueManager


class _WidgetCreated(BaseEvent):
    event_name: ClassVar[str] = "widget.created"
    event_version: ClassVar[str] = "v1"

    widget_name: str = ""


@pytest.fixture
def registry() -> EventRegistry:
    reg = EventRegistry()
    reg.register(_WidgetCreated)
    return reg


def test_register_and_lookup(registry: EventRegistry) -> None:
    assert registry.lookup("widget.created") is _WidgetCreated


def test_is_registered(registry: EventRegistry) -> None:
    assert registry.is_registered("widget.created") is True
    assert registry.is_registered("does.not.exist") is False


def test_lookup_raises_not_found_for_unregistered_event(registry: EventRegistry) -> None:
    with pytest.raises(NotFoundError):
        registry.lookup("does.not.exist")


def test_all_event_names_is_sorted(registry: EventRegistry) -> None:
    assert registry.all_event_names() == ["widget.created"]


def test_register_returns_the_class_for_decorator_use() -> None:
    registry = EventRegistry()

    @registry.register
    class _Foo(BaseEvent):
        event_name: ClassVar[str] = "foo.event"

    assert registry.lookup("foo.event") is _Foo


def test_serialize_event_includes_name_and_version() -> None:
    event = _WidgetCreated(source_service="test-service", widget_name="thing")

    serialized = serialize_event(event)

    assert serialized["event_name"] == "widget.created"
    assert serialized["event_version"] == "v1"
    assert serialized["widget_name"] == "thing"
    assert serialized["source_service"] == "test-service"


def test_deserialize_event_round_trip(registry: EventRegistry) -> None:
    event = _WidgetCreated(source_service="test-service", widget_name="thing")
    serialized = serialize_event(event)

    deserialized = deserialize_event(serialized, registry=registry)

    assert isinstance(deserialized, _WidgetCreated)
    assert deserialized.widget_name == "thing"
    assert deserialized.event_id == event.event_id


def test_base_event_generates_id_and_timestamp_by_default() -> None:
    event = _WidgetCreated(source_service="test-service")

    assert event.event_id is not None
    assert event.timestamp is not None


# --- Integration test against the real RabbitMQ from docker-compose ---
# (queue_manager fixture is provided by conftest.py, skips if unreachable)


async def test_publish_and_subscribe_round_trip(
    queue_manager: QueueManager, registry: EventRegistry
) -> None:
    unique_name = f"widget.created.{uuid.uuid4().hex}"

    class _UniqueEvent(BaseEvent):
        event_name: ClassVar[str] = unique_name
        widget_name: str = ""

    registry.register(_UniqueEvent)

    publisher = EventPublisher(queue_manager)
    subscriber = EventSubscriber(queue_manager, registry=registry)

    received: list[BaseEvent] = []

    async def handler(event: BaseEvent) -> None:
        received.append(event)

    await subscriber.subscribe(unique_name, handler)
    await publisher.publish(_UniqueEvent(source_service="test-service", widget_name="thing"))

    for _ in range(50):
        if received:
            break
        await asyncio.sleep(0.1)

    assert len(received) == 1
    received_event = received[0]
    assert isinstance(received_event, _UniqueEvent)
    assert received_event.widget_name == "thing"
