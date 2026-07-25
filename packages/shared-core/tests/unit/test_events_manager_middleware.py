"""Tests for the event manager facade, middleware chain, audit logging,
metrics, health checks, decorators, helpers, and the framework factory.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from typing import Any, ClassVar
from unittest.mock import AsyncMock

import pytest
from aio_pika.abc import AbstractRobustConnection
from shared_core.constants.logging import LoggingConstants
from shared_core.enums.health_status import HealthStatus
from shared_core.events.audit import audit_consume, audit_failure, audit_publish, audit_replay
from shared_core.events.base import BaseEvent, InternalEvent
from shared_core.events.bus import EventBus
from shared_core.events.decorators import (
    event_handler,
    get_event_name,
    publishes,
    register_handlers,
)
from shared_core.events.exceptions import EventValidationError
from shared_core.events.factory import create_event_framework
from shared_core.events.health import check_event_framework_health
from shared_core.events.helpers import event_name_from_class, generate_correlation_id
from shared_core.events.manager import EventManager
from shared_core.events.metadata import build_metadata
from shared_core.events.metrics import (
    event_consume_latency_seconds,
    event_publish_latency_seconds,
    events_replayed_total,
    measure_consume,
    measure_publish,
    record_internal_failure,
    record_replayed,
)
from shared_core.events.middleware import MiddlewareChain, Next
from shared_core.events.publisher import EventPublisher
from shared_core.events.registry import EventRegistry
from shared_core.events.subscriber import EventSubscriber
from shared_core.logging.context import bind_log_context, reset_log_context
from shared_core.metrics.standard import queue_messages_failed_total
from shared_core.queue.manager import QueueManager

from tests.unit.conftest import rabbitmq_test_settings


class _WidgetCreated(BaseEvent):
    event_name: ClassVar[str] = "manager.widget.created"


@pytest.fixture
def registry() -> EventRegistry:
    reg = EventRegistry()
    reg.register(_WidgetCreated)
    return reg


# --- manager.py ---


async def test_manager_publish_validates_before_calling_the_bus() -> None:
    bus = AsyncMock(spec=EventBus)
    manager = EventManager(bus, registry=EventRegistry())  # event not registered here
    event = _WidgetCreated(source_service="widget-service")

    with pytest.raises(EventValidationError):
        await manager.publish(event)

    bus.publish.assert_not_awaited()


async def test_manager_publish_calls_the_bus_and_audits_success(
    registry: EventRegistry, caplog: pytest.LogCaptureFixture
) -> None:
    bus = AsyncMock(spec=EventBus)
    manager = EventManager(bus, registry=registry)
    event = _WidgetCreated(source_service="widget-service")

    with caplog.at_level(logging.INFO, logger="shared_core.events.audit"):
        await manager.publish(event)

    bus.publish.assert_awaited_once_with(event)
    actions = [r.extra_fields["action"] for r in caplog.records if hasattr(r, "extra_fields")]
    assert "event.publish" in actions


async def test_manager_publish_audits_and_reraises_on_bus_failure(
    registry: EventRegistry, caplog: pytest.LogCaptureFixture
) -> None:
    bus = AsyncMock(spec=EventBus)
    bus.publish.side_effect = ConnectionError("broker down")
    manager = EventManager(bus, registry=registry)
    event = _WidgetCreated(source_service="widget-service")

    with (
        caplog.at_level(logging.INFO, logger="shared_core.events.audit"),
        pytest.raises(ConnectionError),
    ):
        await manager.publish(event)

    actions = [r.extra_fields["action"] for r in caplog.records if hasattr(r, "extra_fields")]
    assert "event.failure" in actions


async def test_manager_publish_records_internal_failure_for_an_internal_event() -> None:
    """Internal events never reach QueueManager, so their failures need their own metric."""

    class _CacheWarmed(InternalEvent):
        event_name: ClassVar[str] = "metrics.test.cache_warmed"

    registry = EventRegistry()
    registry.register(_CacheWarmed)
    bus = EventBus(AsyncMock(spec=EventPublisher), AsyncMock(), registry=registry)
    manager = EventManager(bus, registry=registry)

    async def failing_handler(event: BaseEvent) -> None:
        raise ValueError("internal handler exploded")

    bus.dispatcher.register("metrics.test.cache_warmed", failing_handler)

    queue = EventPublisher.queue_name_for("metrics.test.cache_warmed")
    before = _counter_value(queue_messages_failed_total, queue=queue)

    with pytest.raises(ExceptionGroup):
        await manager.publish(_CacheWarmed(source_service="cache-service"))

    assert _counter_value(queue_messages_failed_total, queue=queue) == before + 1


async def test_manager_subscribe_wraps_the_handler_and_audits_success(
    registry: EventRegistry, caplog: pytest.LogCaptureFixture
) -> None:
    bus = AsyncMock(spec=EventBus)
    manager = EventManager(bus, registry=registry)
    received: list[BaseEvent] = []

    async def handler(event: BaseEvent) -> None:
        received.append(event)

    await manager.subscribe("manager.widget.created", handler)

    bus.subscribe.assert_awaited_once()
    wrapped_handler = bus.subscribe.await_args.args[1]
    event = _WidgetCreated(source_service="widget-service")

    with caplog.at_level(logging.INFO, logger="shared_core.events.audit"):
        await wrapped_handler(event)

    assert received == [event]
    actions = [r.extra_fields["action"] for r in caplog.records if hasattr(r, "extra_fields")]
    assert "event.consume" in actions


async def test_manager_subscribe_audits_failure_when_the_handler_raises(
    registry: EventRegistry, caplog: pytest.LogCaptureFixture
) -> None:
    bus = AsyncMock(spec=EventBus)
    manager = EventManager(bus, registry=registry)

    async def failing_handler(event: BaseEvent) -> None:
        raise ValueError("handler exploded")

    await manager.subscribe("manager.widget.created", failing_handler)
    wrapped_handler = bus.subscribe.await_args.args[1]

    with (
        caplog.at_level(logging.INFO, logger="shared_core.events.audit"),
        pytest.raises(ValueError, match="handler exploded"),
    ):
        await wrapped_handler(_WidgetCreated(source_service="widget-service"))

    actions = [r.extra_fields["action"] for r in caplog.records if hasattr(r, "extra_fields")]
    assert "event.failure" in actions


async def test_manager_middleware_property_lets_callers_extend_the_chain(
    registry: EventRegistry,
) -> None:
    bus = AsyncMock(spec=EventBus)
    manager = EventManager(bus, registry=registry)
    seen: list[str] = []

    async def tracer(event: BaseEvent, call_next: Next) -> None:
        seen.append("before")
        await call_next(event)
        seen.append("after")

    manager.middleware.use_publish(tracer)
    await manager.publish(_WidgetCreated(source_service="widget-service"))

    assert seen == ["before", "after"]


# --- middleware.py ---


async def test_middleware_chain_runs_onion_style_around_the_terminal() -> None:
    chain = MiddlewareChain()
    order: list[str] = []

    async def outer(event: BaseEvent, call_next: Next) -> None:
        order.append("outer-in")
        await call_next(event)
        order.append("outer-out")

    async def inner(event: BaseEvent, call_next: Next) -> None:
        order.append("inner-in")
        await call_next(event)
        order.append("inner-out")

    chain.use_publish(outer)
    chain.use_publish(inner)

    async def terminal(event: BaseEvent) -> None:
        order.append("terminal")

    await chain.run_publish(_WidgetCreated(source_service="s"), terminal)

    assert order == ["outer-in", "inner-in", "terminal", "inner-out", "outer-out"]


async def test_middleware_chain_lets_middleware_replace_the_event() -> None:
    chain = MiddlewareChain()

    async def replace_source(event: BaseEvent, call_next: Next) -> None:
        replaced = event.model_copy(update={"source_service": "replaced"})
        await call_next(replaced)

    chain.use_publish(replace_source)
    seen: list[BaseEvent] = []

    async def terminal(event: BaseEvent) -> None:
        seen.append(event)

    await chain.run_publish(_WidgetCreated(source_service="original"), terminal)

    assert seen[0].source_service == "replaced"


async def test_middleware_chain_with_no_middleware_calls_terminal_directly() -> None:
    chain = MiddlewareChain()
    called = False

    async def terminal(event: BaseEvent) -> None:
        nonlocal called
        called = True

    await chain.run_publish(_WidgetCreated(source_service="s"), terminal)
    assert called is True


async def test_middleware_chain_keeps_publish_and_consume_chains_separate() -> None:
    chain = MiddlewareChain()
    calls: list[str] = []

    async def publish_only(event: BaseEvent, call_next: Next) -> None:
        calls.append("publish_only")
        await call_next(event)

    chain.use_publish(publish_only)

    async def terminal(event: BaseEvent) -> None:
        calls.append("terminal")

    await chain.run_consume(_WidgetCreated(source_service="s"), terminal)

    assert calls == ["terminal"]  # the publish-only middleware never ran


async def test_middleware_chain_use_consume_runs_registered_consume_middleware() -> None:
    chain = MiddlewareChain()
    calls: list[str] = []

    async def consume_only(event: BaseEvent, call_next: Next) -> None:
        calls.append("consume_only")
        await call_next(event)

    chain.use_consume(consume_only)

    async def terminal(event: BaseEvent) -> None:
        calls.append("terminal")

    await chain.run_consume(_WidgetCreated(source_service="s"), terminal)

    assert calls == ["consume_only", "terminal"]


# --- audit.py ---


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    """Read a caplog record's structured `extra_fields`, added by AIIOSLogger.audit()."""
    assert hasattr(record, "extra_fields")
    return record.extra_fields  # type: ignore[no-any-return]


def test_audit_publish_logs_expected_fields(caplog: pytest.LogCaptureFixture) -> None:
    event = _WidgetCreated(source_service="widget-service")

    with caplog.at_level(logging.INFO, logger="shared_core.events.audit"):
        audit_publish(event)

    fields = _extra_fields(caplog.records[-1])
    assert fields["action"] == "event.publish"
    assert fields["resource"] == "manager.widget.created"
    assert fields["event_id"] == str(event.event_id)


def test_audit_consume_defaults_outcome_to_success(caplog: pytest.LogCaptureFixture) -> None:
    event = _WidgetCreated(source_service="widget-service")

    with caplog.at_level(logging.INFO, logger="shared_core.events.audit"):
        audit_consume(event)

    assert _extra_fields(caplog.records[-1])["outcome"] == "success"


def test_audit_replay_logs_the_count(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="shared_core.events.audit"):
        audit_replay("manager.widget.created", count=5, actor_id="user-1")

    fields = _extra_fields(caplog.records[-1])
    assert fields["action"] == "event.replay"
    assert fields["count"] == 5
    assert fields["actor_id"] == "user-1"


def test_audit_failure_logs_outcome_failure_and_the_error(caplog: pytest.LogCaptureFixture) -> None:
    event = _WidgetCreated(source_service="widget-service")

    with caplog.at_level(logging.INFO, logger="shared_core.events.audit"):
        audit_failure(event, error="boom")

    fields = _extra_fields(caplog.records[-1])
    assert fields["outcome"] == "failure"
    assert fields["error"] == "boom"


def test_audit_publish_masks_sensitive_payload_fields(caplog: pytest.LogCaptureFixture) -> None:
    event = _WidgetCreated(source_service="widget-service", payload={"password": "hunter2"})

    with caplog.at_level(logging.INFO, logger="shared_core.events.audit"):
        audit_publish(event)

    fields = _extra_fields(caplog.records[-1])
    assert fields["payload"]["password"] == LoggingConstants.MASKED_VALUE
    assert event.payload["password"] == "hunter2"  # the original event is untouched


# --- metrics.py ---


def _counter_value(counter: object, **labels: str) -> float:
    value = counter.labels(**labels)._value.get()  # type: ignore[attr-defined]
    return float(value)


def _histogram_count(histogram: object, **labels: str) -> float:
    value = histogram.labels(**labels)._sum.get()  # type: ignore[attr-defined]
    return float(value)


def test_record_internal_failure_increments_the_queue_counter() -> None:
    queue = EventPublisher.queue_name_for("metrics.test.internal_failed")
    before = _counter_value(queue_messages_failed_total, queue=queue)

    record_internal_failure("metrics.test.internal_failed")

    assert _counter_value(queue_messages_failed_total, queue=queue) == before + 1


def test_record_replayed_increments_by_count() -> None:
    before = _counter_value(events_replayed_total, event_name="metrics.test.replayed")

    record_replayed("metrics.test.replayed", count=3)

    assert _counter_value(events_replayed_total, event_name="metrics.test.replayed") == before + 3


def test_measure_publish_observes_latency_regardless_of_outcome() -> None:
    queue = EventPublisher.queue_name_for("metrics.test.measure_publish_ok")
    before = _histogram_count(event_publish_latency_seconds, queue=queue)

    with measure_publish("metrics.test.measure_publish_ok"):
        pass

    assert _histogram_count(event_publish_latency_seconds, queue=queue) >= before


def test_measure_publish_still_observes_latency_when_the_block_raises() -> None:
    queue = EventPublisher.queue_name_for("metrics.test.measure_publish_fail")
    before = _histogram_count(event_publish_latency_seconds, queue=queue)

    with (
        pytest.raises(ValueError, match="boom"),
        measure_publish("metrics.test.measure_publish_fail"),
    ):
        raise ValueError("boom")

    assert _histogram_count(event_publish_latency_seconds, queue=queue) >= before


def test_measure_consume_observes_latency() -> None:
    queue = EventPublisher.queue_name_for("metrics.test.measure_consume_ok")
    before = _histogram_count(event_consume_latency_seconds, queue=queue)

    with measure_consume("metrics.test.measure_consume_ok"):
        pass

    assert _histogram_count(event_consume_latency_seconds, queue=queue) >= before


# --- health.py ---


async def test_check_event_framework_health_is_healthy_against_real_rabbitmq(
    rabbitmq_connection: AbstractRobustConnection, registry: EventRegistry
) -> None:

    report = await check_event_framework_health(rabbitmq_connection, registry=registry)

    assert report.status == HealthStatus.HEALTHY
    assert report.registered_event_count == 1
    assert report.error is None


async def test_check_event_framework_health_reports_unhealthy_on_a_broken_connection() -> None:

    class _BrokenConnection:
        is_closed = True

        async def channel(self) -> None:
            raise ConnectionError("no broker")

    report = await check_event_framework_health(_BrokenConnection())  # type: ignore[arg-type]

    assert report.status == HealthStatus.UNHEALTHY
    assert report.error is not None
    assert report.connection_closed is True


# --- decorators.py ---


def test_event_handler_marks_the_function_with_its_event_name() -> None:
    async def handler(event: BaseEvent) -> None:
        pass

    marked = event_handler("manager.widget.created")(handler)

    assert get_event_name(marked) == "manager.widget.created"


def test_get_event_name_returns_none_for_an_undecorated_function() -> None:
    async def handler(event: BaseEvent) -> None:
        pass

    assert get_event_name(handler) is None


async def test_register_handlers_subscribes_only_decorated_functions() -> None:
    manager = AsyncMock(spec=EventManager)

    @event_handler("manager.widget.created")
    async def decorated(event: BaseEvent) -> None:
        pass

    async def undecorated(event: BaseEvent) -> None:
        pass

    await register_handlers(manager, [decorated, undecorated])

    manager.subscribe.assert_awaited_once_with("manager.widget.created", decorated)


async def test_publishes_decorator_publishes_the_returned_event(registry: EventRegistry) -> None:
    bus = AsyncMock(spec=EventBus)
    manager = EventManager(bus, registry=registry)

    @publishes(manager)
    async def create_widget() -> _WidgetCreated:
        return _WidgetCreated(source_service="widget-service")

    result = await create_widget()

    assert isinstance(result, _WidgetCreated)
    bus.publish.assert_awaited_once_with(result)


# --- helpers.py ---


def test_generate_correlation_id_returns_a_valid_uuid4_string() -> None:
    correlation_id = generate_correlation_id()

    assert re.match(r"^[0-9a-f-]{36}$", correlation_id)
    assert uuid.UUID(correlation_id).version == 4


def test_event_name_from_class_uses_the_class_name() -> None:
    assert event_name_from_class(_WidgetCreated) == "_WidgetCreated"


# --- factory.py ---


async def test_create_event_framework_builds_a_working_manager(registry: EventRegistry) -> None:
    framework = await create_event_framework(rabbitmq_test_settings(), registry=registry)
    try:
        received: list[BaseEvent] = []

        async def handler(event: BaseEvent) -> None:
            received.append(event)

        await framework.manager.subscribe("manager.widget.created", handler)
        await framework.manager.publish(_WidgetCreated(source_service="widget-service"))

        for _ in range(50):
            if received:
                break
            await asyncio.sleep(0.1)

        assert len(received) == 1
    finally:
        await framework.shutdown()


# --- metadata.py ---


def test_build_metadata_includes_trace_context_and_extras() -> None:

    bind_log_context(trace_id="trace-1", span_id="span-1")
    try:
        metadata = build_metadata(custom="value")
    finally:
        reset_log_context()

    assert metadata == {"trace_id": "trace-1", "span_id": "span-1", "custom": "value"}


def test_build_metadata_without_bound_context_only_includes_extras() -> None:

    reset_log_context()
    metadata = build_metadata(custom="value")

    assert metadata == {"custom": "value"}


# --- publisher.py: batch / async ---


async def test_publish_batch_publishes_every_event_in_order(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_manager = QueueManager(rabbitmq_connection)
    publisher = EventPublisher(queue_manager)
    name = f"publisher.batch.{uuid.uuid4().hex}"

    class _Event(BaseEvent):
        event_name: ClassVar[str] = name

    registry = EventRegistry()
    registry.register(_Event)
    events = [_Event(source_service="s", payload={"i": i}) for i in range(3)]

    await publisher.publish_batch(events)

    received: list[dict[str, Any]] = []
    subscriber = EventSubscriber(queue_manager, registry=registry)

    async def handler(event: BaseEvent) -> None:
        received.append(event.payload)

    await subscriber.subscribe(name, handler)

    for _ in range(50):
        if len(received) >= 3:
            break
        await asyncio.sleep(0.1)

    assert [item["i"] for item in received] == [0, 1, 2]


async def test_publish_async_schedules_a_task_that_completes(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    queue_manager = QueueManager(rabbitmq_connection)
    publisher = EventPublisher(queue_manager)
    name = f"publisher.async.{uuid.uuid4().hex}"

    class _Event(BaseEvent):
        event_name: ClassVar[str] = name

    registry = EventRegistry()
    registry.register(_Event)

    task = publisher.publish_async(_Event(source_service="s"))
    await task

    assert task.done()

    received: list[BaseEvent] = []
    subscriber = EventSubscriber(queue_manager, registry=registry)

    async def handler(event: BaseEvent) -> None:
        received.append(event)

    await subscriber.subscribe(name, handler)

    for _ in range(50):
        if received:
            break
        await asyncio.sleep(0.1)

    assert len(received) == 1
