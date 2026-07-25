"""Tests for checks.py and dependencies.py, against real infrastructure where applicable."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from aio_pika.abc import AbstractRobustConnection
from redis.asyncio import Redis
from shared_core.enums.health_status import HealthStatus
from shared_core.monitoring.checks import (
    DependencyCheckResult,
    check_http_reachable,
    check_postgresql,
    check_rabbitmq,
    check_redis,
    check_tcp_reachable,
)
from shared_core.monitoring.dependencies import DependencyMonitor
from sqlalchemy.ext.asyncio import AsyncEngine


class _ServerErrorHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        self.send_response(503)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def server_error_url() -> Iterator[str]:
    server = HTTPServer(("localhost", 0), _ServerErrorHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://localhost:{server.server_port}/"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


# --- checks.py: generic primitives ---


async def test_check_tcp_reachable_succeeds_against_a_real_open_port() -> None:
    result = await check_tcp_reachable("rabbitmq", "localhost", 5672)

    assert result.status == HealthStatus.HEALTHY
    assert result.error is None
    assert result.latency_ms >= 0.0


async def test_check_tcp_reachable_reports_unhealthy_for_a_closed_port() -> None:
    result = await check_tcp_reachable("nothing-here", "localhost", 1, timeout_seconds=1.0)

    assert result.status == HealthStatus.UNHEALTHY
    assert result.error is not None


async def test_check_http_reachable_succeeds_against_a_real_server() -> None:
    result = await check_http_reachable("rabbitmq-management", "http://localhost:15672/")

    assert result.status == HealthStatus.HEALTHY
    assert result.error is None


async def test_check_http_reachable_reports_degraded_for_a_real_server_error(
    server_error_url: str,
) -> None:
    result = await check_http_reachable("flaky-service", server_error_url)

    assert result.status == HealthStatus.DEGRADED
    assert result.error == "HTTP 503"


async def test_check_http_reachable_reports_unhealthy_when_unreachable() -> None:
    result = await check_http_reachable("nothing-here", "http://localhost:1/", timeout_seconds=1.0)

    assert result.status == HealthStatus.UNHEALTHY
    assert result.error is not None


# --- checks.py: framework adapters ---


async def test_check_postgresql_adapts_the_database_health_report(pg_engine: AsyncEngine) -> None:
    result = await check_postgresql(pg_engine)

    assert result.name == "postgresql"
    assert result.status == HealthStatus.HEALTHY
    assert result.latency_ms >= 0.0


async def test_check_redis_adapts_the_cache_health_report(real_redis_client: Redis) -> None:
    result = await check_redis(real_redis_client)

    assert result.name == "redis"
    assert result.status == HealthStatus.HEALTHY


async def test_check_rabbitmq_adapts_the_queue_health_report(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    result = await check_rabbitmq(rabbitmq_connection)

    assert result.name == "rabbitmq"
    assert result.status == HealthStatus.HEALTHY


# --- dependencies.py ---


async def test_dependency_monitor_check_all_runs_every_registered_check() -> None:
    monitor = DependencyMonitor()
    monitor.register("a", _healthy_check)
    monitor.register("b", _healthy_check)

    results = await monitor.check_all()

    assert len(results) == 2
    assert all(r.status == HealthStatus.HEALTHY for r in results)


async def test_dependency_monitor_check_all_reports_unhealthy_for_a_raising_check() -> None:
    monitor = DependencyMonitor()
    monitor.register("flaky", _raising_check)

    results = await monitor.check_all()

    assert results[0].status == HealthStatus.UNHEALTHY
    assert results[0].error == "boom"


async def test_dependency_monitor_unregister_removes_the_check() -> None:
    monitor = DependencyMonitor()
    monitor.register("a", _healthy_check)
    monitor.unregister("a")

    results = await monitor.check_all()

    assert results == []


async def test_dependency_monitor_overall_status_is_the_worst_case() -> None:
    monitor = DependencyMonitor()
    monitor.register("healthy", _healthy_check)
    monitor.register("unhealthy", _unhealthy_check)

    assert await monitor.overall_status() == HealthStatus.UNHEALTHY


async def test_dependency_monitor_overall_status_is_healthy_when_nothing_is_registered() -> None:
    monitor = DependencyMonitor()

    assert await monitor.overall_status() == HealthStatus.HEALTHY


async def _healthy_check() -> DependencyCheckResult:
    return DependencyCheckResult(name="ignored", status=HealthStatus.HEALTHY, latency_ms=1.0)


async def _unhealthy_check() -> DependencyCheckResult:
    return DependencyCheckResult(name="ignored", status=HealthStatus.UNHEALTHY, latency_ms=1.0)


async def _raising_check() -> DependencyCheckResult:
    raise RuntimeError("boom")
