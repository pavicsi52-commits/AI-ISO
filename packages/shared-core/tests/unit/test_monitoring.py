"""Tests for the health check framework."""

from __future__ import annotations

from shared_core.enums import HealthStatus
from shared_core.monitoring import HealthChecker


async def test_run_all_reports_healthy_when_every_check_passes() -> None:
    checker = HealthChecker()
    checker.register("database", _healthy)
    checker.register("cache", _healthy)

    result = await checker.run_all()

    assert result.status == HealthStatus.HEALTHY
    assert len(result.checks) == 2


async def test_run_all_reports_unhealthy_when_any_check_fails() -> None:
    checker = HealthChecker()
    checker.register("database", _healthy)
    checker.register("cache", _unhealthy)

    result = await checker.run_all()

    assert result.status == HealthStatus.UNHEALTHY


async def test_run_all_treats_raised_exceptions_as_unhealthy() -> None:
    async def _raises() -> HealthStatus:
        raise RuntimeError("boom")

    checker = HealthChecker()
    checker.register("flaky", _raises)

    result = await checker.run_all()

    assert result.status == HealthStatus.UNHEALTHY
    assert result.checks[0].status == HealthStatus.UNHEALTHY


async def test_run_all_with_no_registered_checks_is_healthy() -> None:
    checker = HealthChecker()

    result = await checker.run_all()

    assert result.status == HealthStatus.HEALTHY
    assert result.checks == []


async def _healthy() -> HealthStatus:
    return HealthStatus.HEALTHY


async def _unhealthy() -> HealthStatus:
    return HealthStatus.UNHEALTHY
