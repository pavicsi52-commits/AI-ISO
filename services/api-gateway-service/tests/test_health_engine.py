"""Tests for app/health/engine.py.

`probe_instance` makes a genuine outbound HTTP call -- pointed at real,
already-running endpoints from the standing infra stack for the healthy
case, and an unroutable loopback port (nothing listens on port 1) for the
unreachable case. Neither uses a mock.
"""

from __future__ import annotations

import pytest
from shared_core.connectors.retry import CircuitBreaker, CircuitState
from shared_core.enums.health_status import HealthStatus as SharedHealthStatus
from shared_core.monitoring.checks import DependencyCheckResult

from app.health.engine import build_circuit_breaker, health_state_from_probe, probe_instance
from app.models.enums import HealthState

pytestmark = pytest.mark.asyncio

_REACHABLE_URL = "http://127.0.0.1:15672/"
"""RabbitMQ's management UI -- confirmed reachable from the standing infra stack."""

_UNREACHABLE_URL = "http://127.0.0.1:1/"
"""A real address nothing listens on -- port 1 is privileged, never bound in this stack."""


class TestProbeInstance:
    async def test_a_reachable_endpoint_probes_healthy(self) -> None:
        result = await probe_instance("rabbitmq-mgmt", _REACHABLE_URL, timeout_seconds=2.0)
        assert result.status == SharedHealthStatus.HEALTHY
        assert result.error is None
        assert result.name == "rabbitmq-mgmt"

    async def test_an_unroutable_address_probes_unhealthy(self) -> None:
        result = await probe_instance("nothing-listening", _UNREACHABLE_URL, timeout_seconds=1.0)
        assert result.status == SharedHealthStatus.UNHEALTHY
        assert result.error is not None
        assert result.name == "nothing-listening"


class TestHealthStateFromProbe:
    async def test_a_real_healthy_probe_translates_to_healthy(self) -> None:
        result = await probe_instance("rabbitmq-mgmt", _REACHABLE_URL, timeout_seconds=2.0)
        assert health_state_from_probe(result) == HealthState.HEALTHY

    async def test_a_real_unreachable_probe_translates_to_unhealthy(self) -> None:
        result = await probe_instance("nothing-listening", _UNREACHABLE_URL, timeout_seconds=1.0)
        assert health_state_from_probe(result) == HealthState.UNHEALTHY

    @pytest.mark.parametrize(
        ("shared_status", "expected"),
        [
            (SharedHealthStatus.HEALTHY, HealthState.HEALTHY),
            (SharedHealthStatus.DEGRADED, HealthState.DEGRADED),
            (SharedHealthStatus.WARNING, HealthState.WARNING),
            (SharedHealthStatus.UNHEALTHY, HealthState.UNHEALTHY),
            (SharedHealthStatus.MAINTENANCE, HealthState.MAINTENANCE),
            (SharedHealthStatus.UNKNOWN, HealthState.UNKNOWN),
        ],
    )
    async def test_every_shared_status_translates_through(
        self, shared_status: SharedHealthStatus, expected: HealthState
    ) -> None:
        # A real DependencyCheckResult value object -- not a mock -- covering every branch
        # `from_shared_health_status` can take, beyond the two `probe_instance` itself can produce.
        result = DependencyCheckResult(name="x", status=shared_status, latency_ms=1.0)
        assert health_state_from_probe(result) == expected


class TestBuildCircuitBreaker:
    async def test_builds_a_real_circuit_breaker_with_the_given_thresholds(self) -> None:
        breaker = build_circuit_breaker(failure_threshold=3, recovery_seconds=15.0)
        assert isinstance(breaker, CircuitBreaker)
        assert breaker.failure_threshold == 3
        assert breaker.recovery_seconds == 15.0
        assert breaker.state == CircuitState.CLOSED
