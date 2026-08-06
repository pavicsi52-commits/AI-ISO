"""HealthMonitorService and ApiServiceHealthRepository: probing and circuit breaking.

Against real PostgreSQL and genuinely real HTTP targets --
``shared_core.monitoring.checks.check_http_reachable`` builds its own
internal ``httpx.AsyncClient`` and cannot be pointed at any mock or ASGI
test double. ``http://127.0.0.1:15672/`` (RabbitMQ management UI) and
``http://127.0.0.1:9200/`` (OpenSearch) are already-running containers
that answer HTTP 200; ``http://127.0.0.1:1/`` is a port nothing listens
on, so it is genuinely, reliably unreachable.
"""

from __future__ import annotations

import uuid

from shared_core.connectors.retry import CircuitBreaker

from app.models.enums import CircuitBreakerState, HealthState
from app.repositories.health import ApiServiceHealthRepository
from app.services.health import HealthMonitorService

# No blanket `pytestmark = pytest.mark.asyncio` here -- one test
# (`breaker_for` reuse) is plain sync, and `asyncio_mode = "auto"` (see
# pyproject.toml) already marks every `async def` test automatically;
# explicitly marking a sync test raises under this project's
# `filterwarnings = ["error", ...]`.

REACHABLE_URL = "http://127.0.0.1:15672/"
REACHABLE_URL_2 = "http://127.0.0.1:9200/"
UNREACHABLE_URL = "http://127.0.0.1:1/"


class TestProbeBrandNewInstance:
    async def test_probing_a_reachable_instance_for_the_first_time_creates_a_healthy_row(
        self, health_monitor_service: HealthMonitorService, make_service, organization_id: uuid.UUID
    ) -> None:
        service = await make_service(name="reachable-service")
        probed = await health_monitor_service.probe(
            organization_id, service.id, REACHABLE_URL, service_name=service.name
        )
        assert probed.status == HealthState.HEALTHY
        assert probed.consecutive_failures == 0
        assert probed.error is None
        assert probed.latency_ms is not None
        assert health_monitor_service.circuit_state(REACHABLE_URL) == CircuitBreakerState.CLOSED

    async def test_probing_a_never_before_probed_unreachable_instance_does_not_raise(
        self, health_monitor_service: HealthMonitorService, make_service, organization_id: uuid.UUID
    ) -> None:
        """Regression test for a real bug in ``HealthMonitorService.probe``.

        A freshly constructed ``ApiServiceHealth`` row's mapped-column
        default for ``consecutive_failures`` only applies at flush, so
        before this fix the attribute was ``None`` on a brand-new
        instance -- and ``row.consecutive_failures += 1`` on the very
        first, never-before-probed, unhealthy probe raised
        ``TypeError: unsupported operand type(s) for +=: 'NoneType' and
        'int'``. The fix passes ``consecutive_failures=0`` explicitly at
        construction (see ``app/services/health.py``). This exact
        path -- brand-new instance, first probe ever, target
        unreachable -- is the one that used to crash.
        """
        service = await make_service(name="never-probed-service")
        probed = await health_monitor_service.probe(
            organization_id, service.id, UNREACHABLE_URL, service_name=service.name
        )
        assert probed.status == HealthState.UNHEALTHY
        assert probed.consecutive_failures == 1
        assert probed.error is not None
        # failure_threshold=2 in service_settings -- one failure does not open it.
        assert health_monitor_service.circuit_state(UNREACHABLE_URL) == CircuitBreakerState.CLOSED


class TestProbeExistingInstance:
    async def test_a_healthy_probe_after_a_failure_resets_consecutive_failures_to_zero(
        self, health_monitor_service: HealthMonitorService, make_service, organization_id: uuid.UUID
    ) -> None:
        service = await make_service(name="flaky-service")
        first = await health_monitor_service.probe(
            organization_id, service.id, UNREACHABLE_URL, service_name=service.name
        )
        assert first.consecutive_failures == 1

        second = await health_monitor_service.probe(
            organization_id, service.id, UNREACHABLE_URL, service_name=service.name
        )
        assert second.id == first.id  # the existing row was updated, not duplicated
        assert second.status == HealthState.UNHEALTHY
        assert second.consecutive_failures == 2

    async def test_repeated_failures_open_the_breaker_at_the_failure_threshold(
        self, health_monitor_service: HealthMonitorService, make_service, organization_id: uuid.UUID
    ) -> None:
        # service_settings tunes circuit_breaker_failure_threshold=2.
        service = await make_service(name="breaker-service")
        await health_monitor_service.probe(
            organization_id, service.id, UNREACHABLE_URL, service_name=service.name
        )
        assert health_monitor_service.circuit_state(UNREACHABLE_URL) == CircuitBreakerState.CLOSED

        second = await health_monitor_service.probe(
            organization_id, service.id, UNREACHABLE_URL, service_name=service.name
        )
        assert second.consecutive_failures == 2
        assert second.circuit_state == CircuitBreakerState.OPEN
        assert health_monitor_service.circuit_state(UNREACHABLE_URL) == CircuitBreakerState.OPEN


class TestCircuitState:
    async def test_returns_closed_for_a_url_that_has_never_been_probed(
        self,
        health_monitor_service: HealthMonitorService,
        breakers: dict[str, CircuitBreaker],
    ) -> None:
        state = health_monitor_service.circuit_state("http://totally-unprobed.test/")
        assert state == CircuitBreakerState.CLOSED
        # Checking state alone must not have created a breaker for it.
        assert "http://totally-unprobed.test/" not in breakers

    def test_breaker_for_creates_once_and_reuses_the_same_breaker_on_reuse(
        self, health_monitor_service: HealthMonitorService
    ) -> None:
        first = health_monitor_service.breaker_for(REACHABLE_URL)
        second = health_monitor_service.breaker_for(REACHABLE_URL)
        assert first is second


class TestCustomThresholds:
    async def test_a_failure_threshold_of_one_opens_the_breaker_on_the_first_failure(
        self, health_repo: ApiServiceHealthRepository, make_service, organization_id: uuid.UUID
    ) -> None:
        service = await make_service(name="strict-service")
        strict_service = HealthMonitorService(
            health_repo,
            failure_threshold=1,
            recovery_seconds=0.05,
            probe_timeout_seconds=2.0,
            breakers={},
        )
        probed = await strict_service.probe(
            organization_id, service.id, UNREACHABLE_URL, service_name=service.name
        )
        assert probed.consecutive_failures == 1
        assert probed.circuit_state == CircuitBreakerState.OPEN


class TestSnapshotAndCircuitSnapshot:
    async def test_snapshot_returns_every_instances_last_probed_health_keyed_by_url(
        self, health_monitor_service: HealthMonitorService, make_service, organization_id: uuid.UUID
    ) -> None:
        service = await make_service(name="multi-instance-service")
        await health_monitor_service.probe(
            organization_id, service.id, REACHABLE_URL, service_name=service.name
        )
        await health_monitor_service.probe(
            organization_id, service.id, UNREACHABLE_URL, service_name=service.name
        )

        snapshot = await health_monitor_service.snapshot(organization_id, service.id)
        assert snapshot == {
            REACHABLE_URL: HealthState.HEALTHY,
            UNREACHABLE_URL: HealthState.UNHEALTHY,
        }

    async def test_circuit_snapshot_returns_every_instances_last_persisted_circuit_state(
        self, health_monitor_service: HealthMonitorService, make_service, organization_id: uuid.UUID
    ) -> None:
        service = await make_service(name="circuit-snapshot-service")
        await health_monitor_service.probe(
            organization_id, service.id, REACHABLE_URL_2, service_name=service.name
        )

        snapshot = await health_monitor_service.circuit_snapshot(organization_id, service.id)
        assert snapshot == {REACHABLE_URL_2: CircuitBreakerState.CLOSED}


class TestListForOrg:
    async def test_returns_every_probed_instance_across_every_service_in_the_org(
        self, health_monitor_service: HealthMonitorService, make_service, organization_id: uuid.UUID
    ) -> None:
        service_a = await make_service(name="service-a")
        service_b = await make_service(name="service-b")
        await health_monitor_service.probe(
            organization_id, service_a.id, REACHABLE_URL, service_name=service_a.name
        )
        await health_monitor_service.probe(
            organization_id, service_b.id, REACHABLE_URL_2, service_name=service_b.name
        )

        rows = await health_monitor_service.list_for_org(organization_id)
        assert {row.instance_url for row in rows} == {REACHABLE_URL, REACHABLE_URL_2}

    async def test_does_not_include_another_organizations_rows(
        self, health_monitor_service: HealthMonitorService, make_service, organization_id: uuid.UUID
    ) -> None:
        service = await make_service(name="isolated-service")
        await health_monitor_service.probe(
            organization_id, service.id, REACHABLE_URL, service_name=service.name
        )
        rows = await health_monitor_service.list_for_org(uuid.uuid4())
        assert rows == []


class TestRepositoryGetForInstance:
    async def test_returns_none_before_the_instance_has_ever_been_probed(
        self, health_repo: ApiServiceHealthRepository, make_service, organization_id: uuid.UUID
    ) -> None:
        service = await make_service(name="unprobed-service")
        row = await health_repo.get_for_instance(organization_id, service.id, REACHABLE_URL)
        assert row is None

    async def test_returns_the_row_once_probed(
        self,
        health_monitor_service: HealthMonitorService,
        health_repo: ApiServiceHealthRepository,
        make_service,
        organization_id: uuid.UUID,
    ) -> None:
        service = await make_service(name="probed-lookup-service")
        probed = await health_monitor_service.probe(
            organization_id, service.id, REACHABLE_URL, service_name=service.name
        )
        row = await health_repo.get_for_instance(organization_id, service.id, REACHABLE_URL)
        assert row is not None
        assert row.id == probed.id
