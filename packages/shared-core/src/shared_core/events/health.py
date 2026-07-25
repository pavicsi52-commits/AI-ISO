"""Event framework health checks.

Per docs/020_Enterprise_Event_Framework.md.txt "MONITORING": "Event
health checks." Confirms the underlying RabbitMQ connection (owned by
:mod:`shared_core.queue`, Prompt 012) is reachable and reports how many
event types are currently registered.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from aio_pika.abc import AbstractRobustConnection

from shared_core.enums.health_status import HealthStatus
from shared_core.events.constants import DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS
from shared_core.events.registry import EventRegistry, default_registry


@dataclass(frozen=True, slots=True)
class EventHealthReport:
    """The result of an event framework health check."""

    status: HealthStatus
    latency_ms: float
    registered_event_count: int
    connection_closed: bool
    error: str | None = None


async def check_event_framework_health(
    connection: AbstractRobustConnection,
    *,
    registry: EventRegistry = default_registry,
    timeout_seconds: float = DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS,
) -> EventHealthReport:
    """Check RabbitMQ connectivity and report the registry's size.

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
    return EventHealthReport(
        status=status,
        latency_ms=latency_ms,
        registered_event_count=len(registry.all_event_names()),
        connection_closed=connection.is_closed,
        error=error,
    )


__all__ = ["EventHealthReport", "check_event_framework_health"]
