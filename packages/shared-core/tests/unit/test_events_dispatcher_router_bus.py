"""Tests for in-process dispatch, glob-pattern routing, and the event bus's
internal/non-internal split.
"""

from __future__ import annotations

from typing import ClassVar
from unittest.mock import AsyncMock

import pytest
from shared_core.events.base import BaseEvent, EventType, InternalEvent
from shared_core.events.bus import EventBus
from shared_core.events.dispatcher import EventDispatcher
from shared_core.events.registry import EventRegistry
from shared_core.events.router import EventRouter


class _WidgetCreated(BaseEvent):
    event_name: ClassVar[str] = "widget.created"


class _WidgetDeleted(BaseEvent):
    event_name: ClassVar[str] = "widget.deleted"


class _CacheWarmed(InternalEvent):
    event_name: ClassVar[str] = "cache.warmed"


# --- dispatcher.py ---


async def test_dispatch_invokes_every_registered_handler_in_priority_order() -> None:
    dispatcher = EventDispatcher()
    order: list[str] = []

    async def first(event: BaseEvent) -> None:
        order.append("first")

    async def second(event: BaseEvent) -> None:
        order.append("second")

    dispatcher.register("widget.created", second, priority=200)
    dispatcher.register("widget.created", first, priority=100)

    invoked = await dispatcher.dispatch(_WidgetCreated(source_service="test"))

    assert order == ["first", "second"]
    assert invoked == 2


async def test_dispatch_skips_handlers_whose_filter_rejects_the_event() -> None:
    dispatcher = EventDispatcher()
    calls: list[BaseEvent] = []

    async def handler(event: BaseEvent) -> None:
        calls.append(event)

    dispatcher.register("widget.created", handler, filter=lambda e: e.source_service == "allowed")

    await dispatcher.dispatch(_WidgetCreated(source_service="blocked"))
    assert calls == []

    await dispatcher.dispatch(_WidgetCreated(source_service="allowed"))
    assert len(calls) == 1


async def test_dispatch_with_no_registered_handlers_invokes_nothing() -> None:
    dispatcher = EventDispatcher()

    invoked = await dispatcher.dispatch(_WidgetCreated(source_service="test"))

    assert invoked == 0


async def test_dispatch_runs_every_handler_even_when_one_raises() -> None:
    dispatcher = EventDispatcher()
    calls: list[str] = []

    async def failing(event: BaseEvent) -> None:
        calls.append("failing")
        raise ValueError("boom")

    async def succeeding(event: BaseEvent) -> None:
        calls.append("succeeding")

    dispatcher.register("widget.created", failing, priority=1)
    dispatcher.register("widget.created", succeeding, priority=2)

    with pytest.raises(ExceptionGroup) as exc_info:
        await dispatcher.dispatch(_WidgetCreated(source_service="test"))

    assert calls == ["failing", "succeeding"]
    assert len(exc_info.value.exceptions) == 1


def test_unregister_removes_only_the_named_handler() -> None:
    dispatcher = EventDispatcher()

    async def handler_a(event: BaseEvent) -> None:
        pass

    async def handler_b(event: BaseEvent) -> None:
        pass

    dispatcher.register("widget.created", handler_a)
    dispatcher.register("widget.created", handler_b)
    dispatcher.unregister("widget.created", handler_a)

    remaining = dispatcher.handlers_for("widget.created")
    assert [reg.handler for reg in remaining] == [handler_b]


def test_unregister_on_an_unknown_event_name_is_a_no_op() -> None:
    dispatcher = EventDispatcher()

    async def handler(event: BaseEvent) -> None:
        pass

    dispatcher.unregister("does.not.exist", handler)  # must not raise


# --- router.py ---


def test_add_route_and_resolve_matches_glob_patterns() -> None:
    router: EventRouter[str] = EventRouter()
    router.add_route("widget.*", "widget-queue")
    router.add_route("order.*", "order-queue")

    assert router.resolve("widget.created") == ["widget-queue"]
    assert router.resolve("order.placed") == ["order-queue"]
    assert router.resolve("invoice.sent") == []


def test_resolve_fans_out_to_every_matching_route() -> None:
    router: EventRouter[str] = EventRouter()
    router.add_route("widget.*", "audit-queue")
    router.add_route("*", "catch-all-queue")

    assert router.resolve("widget.created") == ["audit-queue", "catch-all-queue"]


def test_resolve_respects_an_extra_condition() -> None:
    router: EventRouter[str] = EventRouter()
    router.add_route("widget.*", "vip-queue", condition=lambda name: "created" in name)

    assert router.resolve("widget.created") == ["vip-queue"]
    assert router.resolve("widget.deleted") == []


def test_matches_any() -> None:
    router: EventRouter[str] = EventRouter()
    router.add_route("widget.*", "queue")

    assert router.matches_any("widget.created") is True
    assert router.matches_any("order.placed") is False


def test_clear_removes_every_route() -> None:
    router: EventRouter[str] = EventRouter()
    router.add_route("*", "queue")
    router.clear()

    assert router.resolve("anything") == []


# --- bus.py ---


@pytest.fixture
def registry() -> EventRegistry:
    reg = EventRegistry()
    reg.register(_WidgetCreated)
    reg.register(_WidgetDeleted)
    reg.register(_CacheWarmed)
    return reg


async def test_bus_publish_routes_internal_events_to_the_dispatcher_only(
    registry: EventRegistry,
) -> None:
    publisher = AsyncMock()
    subscriber = AsyncMock()
    dispatcher = EventDispatcher()
    received: list[BaseEvent] = []

    async def handler(event: BaseEvent) -> None:
        received.append(event)

    dispatcher.register("cache.warmed", handler)
    bus = EventBus(publisher, subscriber, dispatcher=dispatcher, registry=registry)

    await bus.publish(_CacheWarmed(source_service="cache-service"))

    assert len(received) == 1
    publisher.publish.assert_not_called()


async def test_bus_publish_routes_non_internal_events_to_the_publisher(
    registry: EventRegistry,
) -> None:
    publisher = AsyncMock()
    subscriber = AsyncMock()
    bus = EventBus(publisher, subscriber, registry=registry)
    event = _WidgetCreated(source_service="widget-service")

    await bus.publish(event)

    publisher.publish.assert_awaited_once_with(event)


async def test_bus_subscribe_routes_internal_events_to_the_dispatcher(
    registry: EventRegistry,
) -> None:
    publisher = AsyncMock()
    subscriber = AsyncMock()
    bus = EventBus(publisher, subscriber, registry=registry)

    async def handler(event: BaseEvent) -> None:
        pass

    await bus.subscribe("cache.warmed", handler)

    subscriber.subscribe.assert_not_awaited()
    assert bus.dispatcher.handlers_for("cache.warmed")


async def test_bus_subscribe_routes_non_internal_events_to_the_subscriber(
    registry: EventRegistry,
) -> None:
    publisher = AsyncMock()
    subscriber = AsyncMock()
    bus = EventBus(publisher, subscriber, registry=registry)

    async def handler(event: BaseEvent) -> None:
        pass

    await bus.subscribe("widget.created", handler)

    subscriber.subscribe.assert_awaited_once_with("widget.created", handler)


def test_internal_event_type_is_never_published_over_the_queue() -> None:
    assert _CacheWarmed.event_type is EventType.INTERNAL
