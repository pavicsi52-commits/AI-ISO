"""The three background workers, against real PostgreSQL.

Each worker gets its own session in production; here that session
factory is the same SAVEPOINT-bound one every other fixture uses, so
data created through the service fixtures in the same test is visible
to the worker's own sessions -- see ``tests/conftest.py``'s
``db_session_factory``.

**Reading back what a worker's own session committed.** A worker
commits through a *new* ``AsyncSession`` object bound to the same
underlying connection, not the fixture's ``db_session``. A fresh query
for rows the fixture session never loaded (a list, a count) sees that
commit immediately -- same connection, same transaction. Re-reading an
object the fixture session already loaded into its own identity map
does not: with ``expire_on_commit=False`` that object is never
refreshed just because another session on the same connection
committed. Those reads go through a brand-new ``db_session_factory()``
session instead, mirroring every prior AI-IOS service's own
``test_workers.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from shared_core.connectors.retry import CircuitBreaker, CircuitState
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import GatewayServiceSettings
from app.models.enums import QuotaKind, QuotaPeriod, QuotaScope
from app.models.request import ApiRequestLog, ApiResponseLog
from app.repositories.governance import ApiStatisticRepository
from app.repositories.health import ApiServiceHealthRepository
from app.repositories.quota import ApiQuotaPolicyRepository
from app.workers.health_probe_sweep import HealthProbeSweepWorker
from app.workers.quota_reset_sweep import QuotaResetSweepWorker
from app.workers.statistics_rollup import StatisticsRollupWorker
from tests.conftest import RecordingPublisher, ago

pytestmark = pytest.mark.asyncio

UNREACHABLE_URL = "http://127.0.0.1:1/"
REACHABLE_URL = "http://127.0.0.1:15672/"
"""RabbitMQ's own management UI -- a real, already-running dependency
from the standing docker-compose stack, per this suite's own ``check_
http_reachable`` gotcha (it builds its own client and cannot be pointed
at an in-process ASGI app)."""


def _flaky_after(
    real_factory: async_sessionmaker[AsyncSession], *, fail_on_call: int
) -> Callable[[], AsyncSession]:
    """A session factory that raises on its *fail_on_call*-th invocation only.

    Simulates one instance's/organization's own session breaking mid-sweep
    without touching any other's -- the workers open one session per
    instance/organization by calling ``session_factory()`` with no
    arguments, so the only way to target "one target's session" from
    outside is by call order.
    """
    calls = {"n": 0}

    def factory() -> AsyncSession:
        calls["n"] += 1
        if calls["n"] == fail_on_call:
            raise RuntimeError("Simulated per-target session failure.")
        return real_factory()

    return factory


class TestHealthProbeSweepWorker:
    async def test_tick_probes_every_enabled_instance_and_persists_health(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: GatewayServiceSettings,
        breakers: dict[str, CircuitBreaker],
        make_service,
        organization_id: uuid.UUID,
    ) -> None:
        service = await make_service(name="reachable-service", instance_url=REACHABLE_URL)

        worker = HealthProbeSweepWorker(db_session_factory, breakers, service_settings)
        probed = await worker.tick()
        assert probed >= 1

        async with db_session_factory() as fresh:
            row = await ApiServiceHealthRepository(fresh).get_for_instance(
                organization_id, service.id, REACHABLE_URL
            )
            assert row is not None
            assert row.status == "healthy"

    async def test_disabled_services_are_skipped(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: GatewayServiceSettings,
        breakers: dict[str, CircuitBreaker],
        make_service,
        service_registry_service,
        organization_id: uuid.UUID,
    ) -> None:
        service = await make_service(name="disabled-service", instance_url=REACHABLE_URL)
        await service_registry_service.update(organization_id, service.id, enabled=False)

        worker = HealthProbeSweepWorker(db_session_factory, breakers, service_settings)
        assert await worker.tick() == 0

    async def test_a_broken_session_for_one_instance_does_not_poison_the_rest(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: GatewayServiceSettings,
        breakers: dict[str, CircuitBreaker],
        make_service,
    ) -> None:
        # `_targets()` itself is call #1 and must succeed; a factory
        # that fails on the *first per-instance* probe (call #2) leaves
        # the second instance's own probe (call #3) unaffected.
        await make_service(name="service-a", instance_url=REACHABLE_URL)
        await make_service(name="service-b", instance_url=UNREACHABLE_URL)

        flaky = _flaky_after(db_session_factory, fail_on_call=2)
        worker = HealthProbeSweepWorker(flaky, breakers, service_settings)  # type: ignore[arg-type]
        probed = await worker.tick()
        assert probed == 1

    async def test_run_job_delegates_to_tick(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: GatewayServiceSettings,
        breakers: dict[str, CircuitBreaker],
    ) -> None:
        worker = HealthProbeSweepWorker(db_session_factory, breakers, service_settings)
        await worker.run_job(None)  # type: ignore[arg-type]

    async def test_publishes_health_changed_only_on_an_actual_transition(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: GatewayServiceSettings,
        breakers: dict[str, CircuitBreaker],
        publisher: RecordingPublisher,
        make_service,
    ) -> None:
        await make_service(name="flaky-instance-service", instance_url=UNREACHABLE_URL)
        worker = HealthProbeSweepWorker(
            db_session_factory, breakers, service_settings, publish_event=publisher
        )

        await worker.tick()
        assert publisher.names == ["GatewayHealthChanged"]
        first_payload = publisher.events[0].payload
        assert first_payload["previous_status"] is None
        assert first_payload["status"] == "unhealthy"

        # Same instance, same resulting status -- no transition, so no
        # second event, even though a probe genuinely ran again.
        await worker.tick()
        assert publisher.names == ["GatewayHealthChanged"]

    async def test_breakers_are_shared_across_probes_within_one_tick(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: GatewayServiceSettings,
        breakers: dict[str, CircuitBreaker],
        make_service,
    ) -> None:
        # Two distinct services, each with its own health row, both
        # pointing at the *same* unreachable URL. `service_settings`'s
        # own `circuit_breaker_failure_threshold` is 2 -- if breakers
        # were per-probe rather than shared by instance URL, neither
        # row would ever see more than a single failure and the breaker
        # would stay CLOSED.
        await make_service(name="shared-a", instance_url=UNREACHABLE_URL)
        await make_service(name="shared-b", instance_url=UNREACHABLE_URL)

        worker = HealthProbeSweepWorker(db_session_factory, breakers, service_settings)
        probed = await worker.tick()
        assert probed == 2
        assert breakers[UNREACHABLE_URL].state is CircuitState.OPEN


class TestStatisticsRollupWorker:
    async def _seed_request(
        self, db_session_factory: async_sessionmaker[AsyncSession], organization_id: uuid.UUID
    ) -> None:
        now = datetime.now(UTC)
        async with db_session_factory() as session:
            request = ApiRequestLog(
                organization_id=organization_id,
                method="GET",
                path="/echo",
                correlation_id=str(uuid.uuid4()),
                started_at=now,
            )
            session.add(request)
            await session.flush()
            session.add(
                ApiResponseLog(
                    organization_id=organization_id,
                    request_id=request.id,
                    status_code=200,
                    latency_ms=12.5,
                    completed_at=now,
                )
            )
            await session.commit()

    async def test_tick_recomputes_every_organization_with_logged_requests(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        organization_id: uuid.UUID,
    ) -> None:
        await self._seed_request(db_session_factory, organization_id)

        worker = StatisticsRollupWorker(db_session_factory, window_seconds=3_600)
        done = await worker.tick()
        assert done >= 1

        async with db_session_factory() as fresh:
            latest = await ApiStatisticRepository(fresh).latest(organization_id)
            assert latest is not None
            assert latest.total_requests >= 1

    async def test_a_tick_with_no_requests_reports_zero(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = StatisticsRollupWorker(db_session_factory, window_seconds=3_600)
        assert await worker.tick() == 0

    async def test_run_job_delegates_to_tick(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = StatisticsRollupWorker(db_session_factory, window_seconds=3_600)
        await worker.run_job(None)  # type: ignore[arg-type]

    async def test_a_failure_recomputing_one_organization_does_not_poison_the_next(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        organization_id: uuid.UUID,
    ) -> None:
        # `_organizations()` itself is call #1 and must succeed; a
        # factory that fails on the *first per-organization* recompute
        # (call #2) leaves the second organization's own recompute
        # (call #3) unaffected -- regardless of which organization the
        # database happens to return first.
        other_organization_id = uuid.uuid4()
        await self._seed_request(db_session_factory, organization_id)
        await self._seed_request(db_session_factory, other_organization_id)

        flaky = _flaky_after(db_session_factory, fail_on_call=2)
        worker = StatisticsRollupWorker(flaky, window_seconds=3_600)  # type: ignore[arg-type]
        done = await worker.tick()
        assert done == 1


class TestQuotaResetSweepWorker:
    async def test_tick_resets_every_due_quota(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        quotas_repo: ApiQuotaPolicyRepository,
        make_quota_policy,
    ) -> None:
        policy = await make_quota_policy(
            scope=QuotaScope.ORGANIZATION,
            kind=QuotaKind.REQUEST,
            period=QuotaPeriod.DAILY,
            limit_value=10,
        )
        policy.used_value = 7
        policy.period_resets_at = ago(1)
        await quotas_repo.update(policy)

        worker = QuotaResetSweepWorker(db_session_factory)
        reset_count = await worker.tick()
        assert reset_count >= 1

        async with db_session_factory() as fresh:
            refreshed = await ApiQuotaPolicyRepository(fresh).require_in_org(
                policy.organization_id, policy.id
            )
            assert refreshed.used_value == 0.0
            assert refreshed.period_resets_at > datetime.now(UTC)

    async def test_a_tick_with_nothing_due_reports_zero(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = QuotaResetSweepWorker(db_session_factory)
        assert await worker.tick() == 0

    async def test_run_job_delegates_to_tick(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = QuotaResetSweepWorker(db_session_factory)
        await worker.run_job(None)  # type: ignore[arg-type]

    async def test_a_totally_broken_session_factory_is_swallowed_for_the_whole_tick(self) -> None:
        # Unlike the other two workers, this one wraps its *entire*
        # tick body in one try/except -- a session that cannot even
        # open must not crash the sweep.
        def _broken() -> AsyncSession:
            raise RuntimeError("Simulated session failure.")

        worker = QuotaResetSweepWorker(_broken)  # type: ignore[arg-type]
        assert await worker.tick() == 0
