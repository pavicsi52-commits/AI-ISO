"""Dependency health checks.

Per docs/023_Enterprise_Monitoring_Framework.md.txt "DEPENDENCY
MONITORING": PostgreSQL, Neo4j, Redis, RabbitMQ, MinIO, OpenSearch,
SMTP, AI Providers, External REST APIs. "Every dependency must expose
health status."

Three dependencies already have a real client wrapper elsewhere in
``shared-core`` (PostgreSQL, Redis, RabbitMQ) -- this module adapts
their existing health functions into one uniform
:class:`DependencyCheckResult` shape. The rest (Neo4j, MinIO,
OpenSearch, SMTP, AI Providers, External REST APIs) don't have a
dedicated client wrapper in this codebase yet, so this module provides
the two generic, protocol-level primitives ("TCP reachable" / "HTTP
reachable") every one of them can be checked with today, without this
framework reimplementing a Neo4j/OpenSearch/SMTP client just to monitor it.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from shared_core.cache.health import check_cache_health
from shared_core.database.health import get_health_report
from shared_core.enums.health_status import HealthStatus
from shared_core.monitoring.constants import DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS
from shared_core.queue.health import check_queue_health

if TYPE_CHECKING:
    from aio_pika.abc import AbstractRobustConnection
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncEngine

_HTTP_SERVER_ERROR_STATUS: int = 500


@dataclass(frozen=True, slots=True)
class DependencyCheckResult:
    """The outcome of checking one monitored dependency."""

    name: str
    status: HealthStatus
    latency_ms: float
    error: str | None = None


async def check_tcp_reachable(
    name: str,
    host: str,
    port: int,
    *,
    timeout_seconds: float = DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS,
) -> DependencyCheckResult:
    """Check whether *host*:*port* accepts a TCP connection.

    Used for any dependency without its own client wrapper in this
    codebase yet (e.g. Neo4j's Bolt port, an SMTP server).
    """
    start = time.perf_counter()
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout_seconds
        )
        writer.close()
        await writer.wait_closed()
        status, error = HealthStatus.HEALTHY, None
    except Exception as exc:
        status, error = HealthStatus.UNHEALTHY, str(exc)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    return DependencyCheckResult(name=name, status=status, latency_ms=latency_ms, error=error)


async def check_http_reachable(
    name: str, url: str, *, timeout_seconds: float = DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS
) -> DependencyCheckResult:
    """Check whether *url* responds with a non-server-error HTTP status.

    Used for any HTTP-based dependency without its own client wrapper
    yet (OpenSearch's REST API, an AI provider, an external REST API).
    """
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(url)
        if response.status_code < _HTTP_SERVER_ERROR_STATUS:
            status, error = HealthStatus.HEALTHY, None
        else:
            status, error = HealthStatus.DEGRADED, f"HTTP {response.status_code}"
    except Exception as exc:
        status, error = HealthStatus.UNHEALTHY, str(exc)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    return DependencyCheckResult(name=name, status=status, latency_ms=latency_ms, error=error)


async def check_postgresql(engine: AsyncEngine) -> DependencyCheckResult:
    """Adapt :func:`shared_core.database.health.get_health_report` (Prompt 018)."""
    report = await get_health_report(engine)
    return DependencyCheckResult(
        name="postgresql", status=report.status, latency_ms=report.latency_ms
    )


async def check_redis(client: Redis) -> DependencyCheckResult:
    """Adapt :func:`shared_core.cache.health.check_cache_health` (Prompt 019)."""
    status, latency_ms = await check_cache_health(client)
    return DependencyCheckResult(name="redis", status=status, latency_ms=latency_ms)


async def check_rabbitmq(connection: AbstractRobustConnection) -> DependencyCheckResult:
    """Adapt :func:`shared_core.queue.health.check_queue_health` (Prompt 021)."""
    report = await check_queue_health(connection)
    return DependencyCheckResult(
        name="rabbitmq", status=report.status, latency_ms=report.latency_ms, error=report.error
    )


__all__ = [
    "DependencyCheckResult",
    "check_http_reachable",
    "check_postgresql",
    "check_rabbitmq",
    "check_redis",
    "check_tcp_reachable",
]
