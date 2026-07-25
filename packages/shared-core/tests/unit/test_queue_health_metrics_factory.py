"""Tests for statistics, metrics, health checks, decorators, factory, and helpers."""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aio_pika.abc import AbstractRobustConnection
from shared_core.enums.health_status import HealthStatus
from shared_core.metrics.standard import (
    queue_messages_consumed_total,
    queue_messages_dead_lettered_total,
    queue_messages_failed_total,
    queue_messages_published_total,
)
from shared_core.queue.consumer import Consumer
from shared_core.queue.decorators import get_job_queue_name, job, register_jobs, scheduled
from shared_core.queue.factory import create_queue_framework
from shared_core.queue.health import check_queue_health, get_queue_depth
from shared_core.queue.helpers import generate_message_id, queue_name_for
from shared_core.queue.manager import QueueManager
from shared_core.queue.metrics import (
    measure_processing,
    queue_depth,
    queue_message_processing_seconds,
    queue_messages_retried_total,
    queue_worker_count,
    record_consumed,
    record_dead_lettered,
    record_failed,
    record_published,
    record_retried,
    set_queue_depth,
    set_worker_count,
)
from shared_core.queue.scheduler import TaskScheduler
from shared_core.queue.statistics import QueueStatistics

from tests.unit.conftest import rabbitmq_test_settings


def _unique_queue_name() -> str:
    return f"health.metrics.test.{uuid.uuid4().hex}"


def _counter_value(counter: object, **labels: str) -> float:
    value = counter.labels(**labels)._value.get()  # type: ignore[attr-defined]
    return float(value)


def _gauge_value(gauge: object, **labels: str) -> float:
    value = gauge.labels(**labels)._value.get()  # type: ignore[attr-defined]
    return float(value)


def _histogram_sum(histogram: object, **labels: str) -> float:
    value = histogram.labels(**labels)._sum.get()  # type: ignore[attr-defined]
    return float(value)


# --- statistics.py ---


def test_queue_statistics_records_every_counter() -> None:
    stats = QueueStatistics()

    stats.record_published()
    stats.record_consumed()
    stats.record_failed()
    stats.record_retried()
    stats.record_dead_lettered()

    assert (stats.published, stats.consumed, stats.failed, stats.retried, stats.dead_lettered) == (
        1,
        1,
        1,
        1,
        1,
    )


def test_queue_statistics_throughput_is_zero_before_any_time_has_passed() -> None:
    stats = QueueStatistics()
    stats.started_at = time.monotonic()  # freshly "now"

    assert stats.publish_throughput_per_second >= 0.0


def test_queue_statistics_failure_ratio() -> None:
    stats = QueueStatistics()
    stats.record_consumed()
    stats.record_consumed()
    stats.record_consumed()
    stats.record_failed()

    assert stats.failure_ratio == pytest.approx(0.25)


def test_queue_statistics_failure_ratio_is_zero_with_no_data() -> None:
    assert QueueStatistics().failure_ratio == 0.0


def test_queue_statistics_reset_zeroes_every_counter() -> None:
    stats = QueueStatistics()
    stats.record_published()
    stats.record_failed()

    stats.reset()

    assert (stats.published, stats.failed) == (0, 0)


# --- metrics.py ---


def test_record_published_increments_the_shared_counter() -> None:
    queue = _unique_queue_name()
    before = _counter_value(queue_messages_published_total, queue=queue)

    record_published(queue)

    assert _counter_value(queue_messages_published_total, queue=queue) == before + 1


def test_record_consumed_increments_the_shared_counter() -> None:
    queue = _unique_queue_name()
    before = _counter_value(queue_messages_consumed_total, queue=queue)

    record_consumed(queue)

    assert _counter_value(queue_messages_consumed_total, queue=queue) == before + 1


def test_record_failed_increments_the_shared_counter() -> None:
    queue = _unique_queue_name()
    before = _counter_value(queue_messages_failed_total, queue=queue)

    record_failed(queue)

    assert _counter_value(queue_messages_failed_total, queue=queue) == before + 1


def test_record_dead_lettered_increments_the_shared_counter() -> None:
    queue = _unique_queue_name()
    before = _counter_value(queue_messages_dead_lettered_total, queue=queue)

    record_dead_lettered(queue)

    assert _counter_value(queue_messages_dead_lettered_total, queue=queue) == before + 1


def test_record_retried_increments_the_queue_specific_counter() -> None:
    queue = _unique_queue_name()
    before = _counter_value(queue_messages_retried_total, queue=queue)

    record_retried(queue)

    assert _counter_value(queue_messages_retried_total, queue=queue) == before + 1


def test_set_worker_count_updates_the_gauge() -> None:
    pool = _unique_queue_name()

    set_worker_count(pool, 5)

    assert _gauge_value(queue_worker_count, pool=pool) == 5.0


def test_set_queue_depth_updates_the_gauge() -> None:
    queue = _unique_queue_name()

    set_queue_depth(queue, 12)

    assert _gauge_value(queue_depth, queue=queue) == 12.0


def test_measure_processing_observes_latency() -> None:
    queue = _unique_queue_name()
    before = _histogram_sum(queue_message_processing_seconds, queue=queue)

    with measure_processing(queue):
        pass

    assert _histogram_sum(queue_message_processing_seconds, queue=queue) >= before


# --- health.py (real RabbitMQ) ---


async def test_check_queue_health_is_healthy_against_a_real_broker(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    stats = QueueStatistics()
    stats.record_published()

    report = await check_queue_health(rabbitmq_connection, statistics=stats)

    assert report.status == HealthStatus.HEALTHY
    assert report.published == 1
    assert report.error is None


async def test_check_queue_health_reports_unhealthy_on_a_broken_connection() -> None:
    class _BrokenConnection:
        is_closed = True

        async def channel(self) -> None:
            raise ConnectionError("no broker")

    report = await check_queue_health(_BrokenConnection())  # type: ignore[arg-type]

    assert report.status == HealthStatus.UNHEALTHY
    assert report.error is not None


async def test_get_queue_depth_reflects_ready_messages(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    """Checked from a *second* QueueManager/channel, not the one that published.

    A channel's own passive-declare ``message_count`` is observed to stay
    stale (0) indefinitely after that *same* channel just published to the
    queue, even waiting several seconds -- a fresh channel (even on the
    same connection) sees the correct count immediately. Real callers of
    ``get_queue_depth`` (a monitoring/health-check path) are a separate
    process from whatever published anyway, so this mirrors real usage.
    """
    publishing_manager = QueueManager(rabbitmq_connection)
    queue_name = _unique_queue_name()
    await publishing_manager.declare_queue_with_dlq(queue_name)
    await publishing_manager.publish(queue_name, {"x": 1})
    await publishing_manager.publish(queue_name, {"x": 2})

    monitoring_manager = QueueManager(rabbitmq_connection)
    depth = None
    for _ in range(30):
        depth = await get_queue_depth(monitoring_manager, queue_name)
        if depth == 2:
            break
        await asyncio.sleep(0.1)

    assert depth == 2


# --- decorators.py ---


def test_job_marks_a_handler_with_its_queue_name() -> None:
    async def handler(message: dict[str, Any]) -> None:
        pass

    marked = job("orders.created")(handler)

    assert get_job_queue_name(marked) == "orders.created"


def test_get_job_queue_name_returns_none_for_an_undecorated_function() -> None:
    async def handler(message: dict[str, Any]) -> None:
        pass

    assert get_job_queue_name(handler) is None


async def test_register_jobs_subscribes_only_decorated_functions() -> None:
    consumer = AsyncMock(spec=Consumer)

    @job("orders.created")
    async def decorated(message: dict[str, Any]) -> None:
        pass

    async def undecorated(message: dict[str, Any]) -> None:
        pass

    await register_jobs(consumer, [decorated, undecorated])

    consumer.subscribe.assert_awaited_once_with("orders.created", decorated)


def test_scheduled_decorator_registers_a_task_immediately() -> None:
    scheduler = TaskScheduler()

    @scheduled(scheduler, "nightly-report", cron="0 0 * * *")
    async def run_report() -> None:
        pass

    assert scheduler.due_tasks(now=datetime(2026, 1, 1, 0, 0, 30, tzinfo=UTC))


# --- helpers.py ---


def test_generate_message_id_returns_a_valid_uuid4_string() -> None:
    message_id = generate_message_id()

    assert re.match(r"^[0-9a-f-]{36}$", message_id)
    assert uuid.UUID(message_id).version == 4


def test_queue_name_for_joins_segments_with_dots() -> None:
    assert queue_name_for("automation", "discovery") == "automation.discovery"


def test_queue_name_for_requires_at_least_one_segment() -> None:
    with pytest.raises(ValueError, match="at least one segment"):
        queue_name_for()


# --- factory.py (real RabbitMQ) ---


async def test_create_queue_framework_builds_a_working_producer_and_consumer() -> None:
    framework = await create_queue_framework(rabbitmq_test_settings())
    try:
        queue_name = _unique_queue_name()
        await framework.manager.declare_queue_with_dlq(queue_name)

        received: list[dict[str, Any]] = []

        async def handler(message: dict[str, Any]) -> None:
            received.append(message)

        await framework.consumer.subscribe(queue_name, handler)
        await framework.producer.publish(queue_name, {"framework": "test"})

        for _ in range(50):
            if received:
                break
            await asyncio.sleep(0.1)

        assert received == [{"framework": "test"}]
        assert isinstance(framework.scheduler, TaskScheduler)
    finally:
        await framework.shutdown()
