"""Queue framework health checks.

Per docs/021_Enterprise_Queue_Framework.md.txt "HEALTH": Broker Health,
Queue Depth, Worker Status, Message Rate, Latency, Consumer Health,
Producer Health.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aio_pika.abc import AbstractRobustConnection

from shared_core.enums.health_status import HealthStatus
from shared_core.queue.constants import DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS
from shared_core.queue.statistics import QueueStatistics

if TYPE_CHECKING:
    from shared_core.queue.manager import QueueManager


@dataclass(frozen=True, slots=True)
class QueueHealthReport:
    """The result of a queue framework health check.

    ``status``/``latency_ms``/``connection_closed`` cover "Broker Health"
    and "Latency"; the counters cover "Message Rate" -- "Consumer
    Health"/"Producer Health" are the same signal read from whichever
    side (a consumer or a producer) calls this with its own statistics.
    """

    status: HealthStatus
    latency_ms: float
    connection_closed: bool
    published: int
    consumed: int
    failed: int
    dead_lettered: int
    throughput_per_second: float
    error: str | None = None


async def check_queue_health(
    connection: AbstractRobustConnection,
    *,
    statistics: QueueStatistics | None = None,
    timeout_seconds: float = DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS,
) -> QueueHealthReport:
    """Check broker connectivity and report statistics.

    Opens (and immediately closes) a throwaway channel as the liveness
    probe -- the cheapest operation that proves the broker is actually
    responding, not just that the TCP connection object still exists.
    """
    start = time.perf_counter()
    error: str | None = None
    try:
        channel = await asyncio.wait_for(connection.channel(), timeout=timeout_seconds)
        await channel.close()
        status = HealthStatus.HEALTHY
    except Exception as exc:
        status = HealthStatus.UNHEALTHY
        error = str(exc)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    stats = statistics or QueueStatistics()
    return QueueHealthReport(
        status=status,
        latency_ms=latency_ms,
        connection_closed=connection.is_closed,
        published=stats.published,
        consumed=stats.consumed,
        failed=stats.failed,
        dead_lettered=stats.dead_lettered,
        throughput_per_second=stats.consume_throughput_per_second,
        error=error,
    )


async def get_queue_depth(queue_manager: QueueManager, queue_name: str) -> int:
    """Return the number of ready (unconsumed) messages in *queue_name* ("Queue Depth")."""
    channel = await queue_manager.channel()
    queue = await channel.declare_queue(queue_name, durable=True, passive=True)
    return queue.declaration_result.message_count or 0


__all__ = ["QueueHealthReport", "check_queue_health", "get_queue_depth"]
