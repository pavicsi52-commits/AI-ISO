"""The four background workers, against real PostgreSQL and real outbound
HTTP/TCP reachability checks.

Each worker gets its own session in production; here that session
factory is the same SAVEPOINT-bound one every other fixture uses, so
data created through the service fixtures in the same test is visible
to the worker's own sessions -- see ``tests/conftest.py``'s
``db_session_factory``.

**Reading back what a worker's own session committed.** A worker
commits through a *new* ``AsyncSession`` object bound to the same
underlying connection, not the fixture's own ``db_session``. A fresh
query for rows the fixture session never loaded (a list, a count, a
``require_in_org``) sees that commit immediately -- same connection,
same transaction. Re-reading an object the fixture session already
loaded into its own identity map does not: with ``expire_on_commit=
False`` that object is never refreshed just because another session on
the same connection committed. Those reads go through a brand-new
``db_session_factory()`` session instead, mirroring
``../webhook-service/tests/test_workers.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from shared_core.connectors.credentials import CredentialType
from shared_core.enums.health_status import HealthStatus
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import IntegrationHubServiceSettings
from app.models.connector import Connector
from app.models.enums import (
    ConnectorCategory,
    CredentialStatus,
    FlowRunStatus,
    FlowStatus,
    FlowTrigger,
    SyncStatus,
)
from app.models.sync import ConnectorSyncJob
from app.repositories.connector import ConnectorRepository
from app.repositories.credential import ConnectorCredentialRepository
from app.repositories.flow import ConnectorFlowRepository
from app.repositories.governance import ConnectorStatisticRepository
from app.repositories.health import ConnectorHealthRepository
from app.repositories.sync import ConnectorSyncJobRepository
from app.services.connector import ConnectorService
from app.services.credential import CredentialService
from app.services.flow import FlowService
from app.workers.credential_expiry_sweep import CredentialExpirySweepWorker
from app.workers.flow_scheduler_sweep import FlowSchedulerSweepWorker
from app.workers.health_probe_sweep import HealthProbeSweepWorker
from app.workers.statistics_rollup import StatisticsRollupWorker
from tests.conftest import (
    REACHABLE_HTTP_URL,
    REACHABLE_TCP_HOST,
    REACHABLE_TCP_PORT,
    UNREACHABLE_HTTP_URL,
    UNREACHABLE_TCP_HOST,
    UNREACHABLE_TCP_PORT,
    MakeConnectorFn,
    MakeCredentialFn,
    RecordingPublisher,
    ago,
    soon,
    utcnow,
)

pytestmark = pytest.mark.asyncio

_NOOP_DEFINITION = {
    "start": "s1",
    "steps": {"s1": {"kind": "action", "action": "noop", "next": None}},
}
"""A minimal flow definition -- one no-op action step -- so the flow
scheduler sweep's own run succeeds without needing a real connector or
sync/transform/event collaborator wired up."""


def _flaky_after(
    real_factory: async_sessionmaker[AsyncSession], *, fail_on_call: int
) -> Callable[[], AsyncSession]:
    """A session factory that raises on its *fail_on_call*-th invocation only.

    Simulates one item's own session breaking mid-sweep without touching
    any other's -- these workers open one session per item by calling
    ``session_factory()`` with no arguments, so the only way to target
    "one item's session" from outside is by call order.
    """
    calls = {"n": 0}

    def factory() -> AsyncSession:
        calls["n"] += 1
        if calls["n"] == fail_on_call:
            raise RuntimeError("Simulated per-item session failure.")
        return real_factory()

    return factory


async def _enabled_connector(
    connector_service: ConnectorService,
    organization_id: uuid.UUID,
    *,
    name: str = "probe-connector",
    endpoint_url: str | None = None,
    host: str | None = None,
    port: int | None = None,
) -> Connector:
    """Register, configure with a checkable endpoint, and enable one connector."""
    connector = await connector_service.register(
        organization_id, name=name, category=ConnectorCategory.CUSTOM, connector_type="rest_api"
    )
    config: dict[str, object] = {}
    if endpoint_url is not None:
        config["endpoint_url"] = endpoint_url
    if host is not None:
        config["host"] = host
        config["port"] = port
    await connector_service.configure(organization_id, connector.id, config=config)
    return await connector_service.enable(organization_id, connector.id)


class TestHealthProbeSweepWorker:
    async def test_a_tick_with_nothing_due_reports_zero(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: IntegrationHubServiceSettings,
    ) -> None:
        worker = HealthProbeSweepWorker(
            db_session_factory,
            timeout_seconds=service_settings.health_check_timeout_seconds,
            failure_threshold=service_settings.health_failure_threshold,
        )
        assert await worker.tick() == 0

    async def test_tick_probes_a_reachable_connector_and_records_healthy(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: IntegrationHubServiceSettings,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
    ) -> None:
        connector = await _enabled_connector(
            connector_service, organization_id, endpoint_url=REACHABLE_HTTP_URL
        )
        worker = HealthProbeSweepWorker(
            db_session_factory,
            timeout_seconds=service_settings.health_check_timeout_seconds,
            failure_threshold=service_settings.health_failure_threshold,
        )
        probed = await worker.tick()
        assert probed == 1

        async with db_session_factory() as fresh:
            latest = await ConnectorHealthRepository(fresh).latest_for_connector(connector.id)
            assert latest is not None
            assert latest.status == HealthStatus.HEALTHY
            refreshed = await ConnectorRepository(fresh).require_in_org(
                organization_id, connector.id
            )
            assert refreshed.consecutive_failures == 0
            assert refreshed.last_health_check_at is not None

    async def test_tick_probes_an_unreachable_connector_and_records_the_failure(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: IntegrationHubServiceSettings,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
    ) -> None:
        connector = await _enabled_connector(
            connector_service, organization_id, endpoint_url=UNREACHABLE_HTTP_URL
        )
        worker = HealthProbeSweepWorker(
            db_session_factory,
            timeout_seconds=service_settings.health_check_timeout_seconds,
            failure_threshold=service_settings.health_failure_threshold,
        )
        probed = await worker.tick()
        assert probed == 1

        async with db_session_factory() as fresh:
            latest = await ConnectorHealthRepository(fresh).latest_for_connector(connector.id)
            assert latest is not None
            assert latest.status != HealthStatus.HEALTHY
            refreshed = await ConnectorRepository(fresh).require_in_org(
                organization_id, connector.id
            )
            assert refreshed.consecutive_failures == 1

    async def test_a_reachable_tcp_connector_is_probed_over_raw_tcp(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: IntegrationHubServiceSettings,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
    ) -> None:
        connector = await _enabled_connector(
            connector_service,
            organization_id,
            host=REACHABLE_TCP_HOST,
            port=REACHABLE_TCP_PORT,
        )
        worker = HealthProbeSweepWorker(
            db_session_factory,
            timeout_seconds=service_settings.health_check_timeout_seconds,
            failure_threshold=service_settings.health_failure_threshold,
        )
        assert await worker.tick() == 1

        async with db_session_factory() as fresh:
            latest = await ConnectorHealthRepository(fresh).latest_for_connector(connector.id)
            assert latest is not None
            assert latest.status == HealthStatus.HEALTHY

    async def test_an_unreachable_tcp_connector_is_recorded_as_unhealthy(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: IntegrationHubServiceSettings,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
    ) -> None:
        connector = await _enabled_connector(
            connector_service,
            organization_id,
            host=UNREACHABLE_TCP_HOST,
            port=UNREACHABLE_TCP_PORT,
        )
        worker = HealthProbeSweepWorker(
            db_session_factory,
            timeout_seconds=service_settings.health_check_timeout_seconds,
            failure_threshold=service_settings.health_failure_threshold,
        )
        assert await worker.tick() == 1

        async with db_session_factory() as fresh:
            latest = await ConnectorHealthRepository(fresh).latest_for_connector(connector.id)
            assert latest is not None
            assert latest.status != HealthStatus.HEALTHY

    async def test_a_connector_with_no_checkable_endpoint_is_still_probed_as_unknown(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: IntegrationHubServiceSettings,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
    ) -> None:
        connector = await _enabled_connector(connector_service, organization_id)
        worker = HealthProbeSweepWorker(
            db_session_factory,
            timeout_seconds=service_settings.health_check_timeout_seconds,
            failure_threshold=service_settings.health_failure_threshold,
        )
        assert await worker.tick() == 1

        async with db_session_factory() as fresh:
            latest = await ConnectorHealthRepository(fresh).latest_for_connector(connector.id)
            assert latest is not None
            assert latest.status == HealthStatus.UNKNOWN

    async def test_tick_probes_enabled_connectors_across_organizations(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: IntegrationHubServiceSettings,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
    ) -> None:
        other_organization_id = uuid.uuid4()
        connector_a = await _enabled_connector(
            connector_service, organization_id, name="org-a", endpoint_url=REACHABLE_HTTP_URL
        )
        connector_b = await _enabled_connector(
            connector_service,
            other_organization_id,
            name="org-b",
            endpoint_url=UNREACHABLE_HTTP_URL,
        )

        worker = HealthProbeSweepWorker(
            db_session_factory,
            timeout_seconds=service_settings.health_check_timeout_seconds,
            failure_threshold=service_settings.health_failure_threshold,
        )
        assert await worker.tick() == 2

        async with db_session_factory() as fresh:
            health_repo = ConnectorHealthRepository(fresh)
            latest_a = await health_repo.latest_for_connector(connector_a.id)
            latest_b = await health_repo.latest_for_connector(connector_b.id)
            assert latest_a is not None and latest_a.status == HealthStatus.HEALTHY
            assert latest_b is not None and latest_b.status != HealthStatus.HEALTHY

    async def test_a_disabled_connector_is_never_probed(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: IntegrationHubServiceSettings,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
    ) -> None:
        connector = await connector_service.register(
            organization_id,
            name="never-enabled",
            category=ConnectorCategory.CUSTOM,
            connector_type="rest_api",
        )
        await connector_service.configure(
            organization_id, connector.id, config={"endpoint_url": REACHABLE_HTTP_URL}
        )
        # Deliberately never enabled.

        worker = HealthProbeSweepWorker(
            db_session_factory,
            timeout_seconds=service_settings.health_check_timeout_seconds,
            failure_threshold=service_settings.health_failure_threshold,
        )
        assert await worker.tick() == 0

    async def test_a_connectors_own_probe_failure_does_not_poison_the_rest(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: IntegrationHubServiceSettings,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
    ) -> None:
        connector_a = await _enabled_connector(
            connector_service, organization_id, name="first", endpoint_url=REACHABLE_HTTP_URL
        )
        connector_b = await _enabled_connector(
            connector_service, organization_id, name="second", endpoint_url=REACHABLE_HTTP_URL
        )

        # `_due_connectors` itself is call #1 and must succeed; a factory
        # that fails on the *first per-connector* probe session (call #2)
        # leaves the second connector's own probe (call #3) unaffected.
        flaky = _flaky_after(db_session_factory, fail_on_call=2)
        worker = HealthProbeSweepWorker(
            flaky,  # type: ignore[arg-type]
            timeout_seconds=service_settings.health_check_timeout_seconds,
            failure_threshold=service_settings.health_failure_threshold,
        )
        probed = await worker.tick()
        assert probed == 1

        async with db_session_factory() as fresh:
            health_repo = ConnectorHealthRepository(fresh)
            recorded = await health_repo.list_for_connector(
                connector_a.id, limit=5
            ) + await health_repo.list_for_connector(connector_b.id, limit=5)
            assert len(recorded) == 1

    async def test_run_job_delegates_to_tick(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: IntegrationHubServiceSettings,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
    ) -> None:
        connector = await _enabled_connector(
            connector_service, organization_id, endpoint_url=REACHABLE_HTTP_URL
        )
        worker = HealthProbeSweepWorker(
            db_session_factory,
            timeout_seconds=service_settings.health_check_timeout_seconds,
            failure_threshold=service_settings.health_failure_threshold,
        )
        await worker.run_job(None)  # type: ignore[arg-type]

        async with db_session_factory() as fresh:
            latest = await ConnectorHealthRepository(fresh).latest_for_connector(connector.id)
            assert latest is not None

    async def test_the_health_changed_event_fires_only_on_a_healthy_to_unhealthy_transition(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: IntegrationHubServiceSettings,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
    ) -> None:
        await _enabled_connector(
            connector_service, organization_id, endpoint_url=UNREACHABLE_HTTP_URL
        )
        worker_publisher = RecordingPublisher()
        worker = HealthProbeSweepWorker(
            db_session_factory,
            timeout_seconds=service_settings.health_check_timeout_seconds,
            failure_threshold=service_settings.health_failure_threshold,
            publish_event=worker_publisher,
        )

        # First probe: healthy (consecutive_failures == 0) -> unhealthy is a
        # genuine change, so exactly one event fires.
        await worker.tick()
        assert worker_publisher.names == ["ConnectorHealthChanged"]

        # Second probe: already unhealthy -> still unhealthy is *not* a
        # change, so no additional event fires.
        await worker.tick()
        assert worker_publisher.names == ["ConnectorHealthChanged"]

    async def test_no_event_fires_when_a_healthy_connector_stays_healthy(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: IntegrationHubServiceSettings,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
    ) -> None:
        await _enabled_connector(
            connector_service, organization_id, endpoint_url=REACHABLE_HTTP_URL
        )
        worker_publisher = RecordingPublisher()
        worker = HealthProbeSweepWorker(
            db_session_factory,
            timeout_seconds=service_settings.health_check_timeout_seconds,
            failure_threshold=service_settings.health_failure_threshold,
            publish_event=worker_publisher,
        )
        await worker.tick()
        assert worker_publisher.names == []


class TestCredentialExpirySweepWorker:
    async def test_a_tick_with_nothing_due_reports_zero(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: IntegrationHubServiceSettings,
    ) -> None:
        worker = CredentialExpirySweepWorker(
            db_session_factory, encryption_key=service_settings.secret_encryption_key
        )
        assert await worker.tick() == 0

    async def test_tick_expires_a_past_due_active_credential(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: IntegrationHubServiceSettings,
        make_connector: MakeConnectorFn,
        make_credential: MakeCredentialFn,
        organization_id: uuid.UUID,
    ) -> None:
        connector = await make_connector()
        credential = await make_credential(connector.id, expires_at=ago(3_600))

        worker = CredentialExpirySweepWorker(
            db_session_factory, encryption_key=service_settings.secret_encryption_key
        )
        expired = await worker.tick()
        assert expired == 1

        async with db_session_factory() as fresh:
            refreshed = await ConnectorCredentialRepository(fresh).require_in_org(
                organization_id, credential.id
            )
            assert refreshed.status == CredentialStatus.EXPIRED

    async def test_a_credential_not_yet_due_is_left_alone(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: IntegrationHubServiceSettings,
        make_connector: MakeConnectorFn,
        make_credential: MakeCredentialFn,
        organization_id: uuid.UUID,
    ) -> None:
        connector = await make_connector()
        credential = await make_credential(connector.id, expires_at=soon(3_600))

        worker = CredentialExpirySweepWorker(
            db_session_factory, encryption_key=service_settings.secret_encryption_key
        )
        assert await worker.tick() == 0

        async with db_session_factory() as fresh:
            refreshed = await ConnectorCredentialRepository(fresh).require_in_org(
                organization_id, credential.id
            )
            assert refreshed.status == CredentialStatus.ACTIVE

    async def test_a_credential_with_no_expiry_is_left_alone(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: IntegrationHubServiceSettings,
        make_connector: MakeConnectorFn,
        make_credential: MakeCredentialFn,
    ) -> None:
        connector = await make_connector()
        await make_credential(connector.id)  # expires_at defaults to None

        worker = CredentialExpirySweepWorker(
            db_session_factory, encryption_key=service_settings.secret_encryption_key
        )
        assert await worker.tick() == 0

    async def test_tick_expires_credentials_across_organizations(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: IntegrationHubServiceSettings,
        connector_service: ConnectorService,
        make_connector: MakeConnectorFn,
        make_credential: MakeCredentialFn,
        organization_id: uuid.UUID,
    ) -> None:
        other_organization_id = uuid.uuid4()
        connector_a = await make_connector()
        credential_a = await make_credential(connector_a.id, expires_at=ago(60))

        connector_b = await connector_service.register(
            other_organization_id,
            name="other-org-connector",
            category=ConnectorCategory.CUSTOM,
            connector_type="rest_api",
        )
        async with db_session_factory() as other_org_session:
            credential_service_other = CredentialService(
                ConnectorCredentialRepository(other_org_session),
                encryption_key=service_settings.secret_encryption_key,
            )
            credential_b = await credential_service_other.assign(
                other_organization_id,
                connector_id=connector_b.id,
                credential_type=CredentialType.API_KEY,
                raw_value="other-org-secret",
                expires_at=ago(60),
            )
            await other_org_session.commit()

        worker = CredentialExpirySweepWorker(
            db_session_factory, encryption_key=service_settings.secret_encryption_key
        )
        expired = await worker.tick()
        assert expired == 2

        async with db_session_factory() as fresh:
            repo = ConnectorCredentialRepository(fresh)
            refreshed_a = await repo.require_in_org(organization_id, credential_a.id)
            refreshed_b = await repo.require_in_org(other_organization_id, credential_b.id)
            assert refreshed_a.status == CredentialStatus.EXPIRED
            assert refreshed_b.status == CredentialStatus.EXPIRED

    async def test_run_job_delegates_to_tick(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: IntegrationHubServiceSettings,
        make_connector: MakeConnectorFn,
        make_credential: MakeCredentialFn,
        organization_id: uuid.UUID,
    ) -> None:
        connector = await make_connector()
        credential = await make_credential(connector.id, expires_at=ago(60))

        worker = CredentialExpirySweepWorker(
            db_session_factory, encryption_key=service_settings.secret_encryption_key
        )
        await worker.run_job(None)  # type: ignore[arg-type]

        async with db_session_factory() as fresh:
            refreshed = await ConnectorCredentialRepository(fresh).require_in_org(
                organization_id, credential.id
            )
            assert refreshed.status == CredentialStatus.EXPIRED

    async def test_a_totally_broken_session_factory_is_swallowed_for_the_whole_tick(self) -> None:
        # This worker runs the entire tick body -- list + every
        # mark_expired + commit -- inside one session and one try/except;
        # unlike the other three workers it does not open one session per
        # item, so a session that cannot even open must not crash the
        # sweep, and any per-item failure would poison the whole tick
        # rather than being isolated (there is no per-item transaction
        # boundary to isolate it with).
        def _broken() -> AsyncSession:
            raise RuntimeError("Simulated session failure.")

        worker = CredentialExpirySweepWorker(_broken, encryption_key="unused")  # type: ignore[arg-type]
        assert await worker.tick() == 0


class TestFlowSchedulerSweepWorker:
    async def test_a_tick_with_nothing_due_reports_zero(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = FlowSchedulerSweepWorker(db_session_factory)
        assert await worker.tick() == 0

    async def test_tick_runs_a_never_run_due_scheduled_flow(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        flow_service: FlowService,
        organization_id: uuid.UUID,
    ) -> None:
        flow = await flow_service.create(
            organization_id,
            name="never-run-flow",
            definition=_NOOP_DEFINITION,
            trigger=FlowTrigger.SCHEDULED,
            schedule_interval_seconds=1,
        )
        await flow_service.activate(organization_id, flow.id)
        assert flow.last_run_at is None

        worker = FlowSchedulerSweepWorker(db_session_factory)
        run = await worker.tick()
        assert run == 1

        async with db_session_factory() as fresh:
            refreshed = await ConnectorFlowRepository(fresh).require_in_org(
                organization_id, flow.id
            )
            assert refreshed.last_run_status == FlowRunStatus.SUCCEEDED
            assert refreshed.run_count == 1
            assert refreshed.last_run_at is not None

    async def test_a_flow_run_recently_within_its_own_interval_is_left_alone(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        flow_service: FlowService,
        flows_repo: ConnectorFlowRepository,
        organization_id: uuid.UUID,
    ) -> None:
        flow = await flow_service.create(
            organization_id,
            name="recently-run-flow",
            definition=_NOOP_DEFINITION,
            trigger=FlowTrigger.SCHEDULED,
            schedule_interval_seconds=3_600,
        )
        await flow_service.activate(organization_id, flow.id)
        flow.last_run_at = utcnow()
        await flows_repo.update(flow)

        worker = FlowSchedulerSweepWorker(db_session_factory)
        assert await worker.tick() == 0

    async def test_a_draft_flow_matching_the_schedule_shape_is_never_picked_up(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        flow_service: FlowService,
        flows_repo: ConnectorFlowRepository,
        organization_id: uuid.UUID,
    ) -> None:
        flow = await flow_service.create(
            organization_id,
            name="draft-flow",
            definition=_NOOP_DEFINITION,
            trigger=FlowTrigger.SCHEDULED,
            schedule_interval_seconds=1,
        )
        assert flow.status == FlowStatus.DRAFT
        # `list_due_for_schedule` itself only narrows on `enabled`/
        # `trigger`/`schedule_interval_seconds` -- force `enabled=True`
        # directly (bypassing the service layer, which never produces
        # this combination) so this test actually exercises the worker's
        # own `row.status != FlowStatus.ACTIVE: continue` guard rather
        # than being trivially excluded by `enabled=False` already.
        flow.enabled = True
        await flows_repo.update(flow)

        worker = FlowSchedulerSweepWorker(db_session_factory)
        assert await worker.tick() == 0

    async def test_a_disabled_flow_matching_the_schedule_shape_is_never_picked_up(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        flow_service: FlowService,
        flows_repo: ConnectorFlowRepository,
        organization_id: uuid.UUID,
    ) -> None:
        flow = await flow_service.create(
            organization_id,
            name="disabled-flow",
            definition=_NOOP_DEFINITION,
            trigger=FlowTrigger.SCHEDULED,
            schedule_interval_seconds=1,
        )
        await flow_service.activate(organization_id, flow.id)
        await flow_service.disable(organization_id, flow.id)
        refreshed = await flow_service.get(organization_id, flow.id)
        assert refreshed.status == FlowStatus.DISABLED
        # Same "bypass the service layer" reasoning as the DRAFT case above.
        refreshed.enabled = True
        await flows_repo.update(refreshed)

        worker = FlowSchedulerSweepWorker(db_session_factory)
        assert await worker.tick() == 0

    async def test_tick_runs_due_flows_across_organizations(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        flow_service: FlowService,
        organization_id: uuid.UUID,
    ) -> None:
        other_organization_id = uuid.uuid4()
        flow_a = await flow_service.create(
            organization_id,
            name="org-a-flow",
            definition=_NOOP_DEFINITION,
            trigger=FlowTrigger.SCHEDULED,
            schedule_interval_seconds=1,
        )
        await flow_service.activate(organization_id, flow_a.id)
        flow_b = await flow_service.create(
            other_organization_id,
            name="org-b-flow",
            definition=_NOOP_DEFINITION,
            trigger=FlowTrigger.SCHEDULED,
            schedule_interval_seconds=1,
        )
        await flow_service.activate(other_organization_id, flow_b.id)

        worker = FlowSchedulerSweepWorker(db_session_factory)
        assert await worker.tick() == 2

        async with db_session_factory() as fresh:
            flows_repo = ConnectorFlowRepository(fresh)
            refreshed_a = await flows_repo.require_in_org(organization_id, flow_a.id)
            refreshed_b = await flows_repo.require_in_org(other_organization_id, flow_b.id)
            assert refreshed_a.last_run_status == FlowRunStatus.SUCCEEDED
            assert refreshed_b.last_run_status == FlowRunStatus.SUCCEEDED

    async def test_a_flows_own_run_failure_does_not_poison_the_rest(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        flow_service: FlowService,
        organization_id: uuid.UUID,
    ) -> None:
        flow_first = await flow_service.create(
            organization_id,
            name="first-flow",
            definition=_NOOP_DEFINITION,
            trigger=FlowTrigger.SCHEDULED,
            schedule_interval_seconds=1,
        )
        await flow_service.activate(organization_id, flow_first.id)
        flow_second = await flow_service.create(
            organization_id,
            name="second-flow",
            definition=_NOOP_DEFINITION,
            trigger=FlowTrigger.SCHEDULED,
            schedule_interval_seconds=1,
        )
        await flow_service.activate(organization_id, flow_second.id)

        # `_due_flow_ids` itself is call #1 and must succeed; a factory
        # that fails on the *first per-flow* run session (call #2) leaves
        # the second flow's own run (call #3) unaffected.
        flaky = _flaky_after(db_session_factory, fail_on_call=2)
        worker = FlowSchedulerSweepWorker(flaky)  # type: ignore[arg-type]
        run = await worker.tick()
        assert run == 1

        async with db_session_factory() as fresh:
            flows_repo = ConnectorFlowRepository(fresh)
            refreshed_first = await flows_repo.require_in_org(organization_id, flow_first.id)
            refreshed_second = await flows_repo.require_in_org(organization_id, flow_second.id)
            statuses = {refreshed_first.last_run_status, refreshed_second.last_run_status}
            assert statuses == {FlowRunStatus.NEVER_RUN, FlowRunStatus.SUCCEEDED}

    async def test_run_job_delegates_to_tick(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        flow_service: FlowService,
        organization_id: uuid.UUID,
    ) -> None:
        flow = await flow_service.create(
            organization_id,
            name="run-job-flow",
            definition=_NOOP_DEFINITION,
            trigger=FlowTrigger.SCHEDULED,
            schedule_interval_seconds=1,
        )
        await flow_service.activate(organization_id, flow.id)

        worker = FlowSchedulerSweepWorker(db_session_factory)
        await worker.run_job(None)  # type: ignore[arg-type]

        async with db_session_factory() as fresh:
            refreshed = await ConnectorFlowRepository(fresh).require_in_org(
                organization_id, flow.id
            )
            assert refreshed.last_run_status == FlowRunStatus.SUCCEEDED


def _seed_sync_job(
    *,
    organization_id: uuid.UUID,
    connector_id: uuid.UUID,
    status: SyncStatus,
    records_processed: int,
    records_succeeded: int,
    records_failed: int,
) -> ConnectorSyncJob:
    return ConnectorSyncJob(
        organization_id=organization_id,
        connector_id=connector_id,
        status=status,
        records_processed=records_processed,
        records_succeeded=records_succeeded,
        records_failed=records_failed,
    )


class TestStatisticsRollupWorker:
    async def test_a_tick_with_nothing_due_reports_zero(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = StatisticsRollupWorker(db_session_factory, window_seconds=3_600)
        assert await worker.tick() == 0

    async def test_tick_rolls_up_one_organizations_sync_jobs_accurately(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        sync_jobs_repo: ConnectorSyncJobRepository,
        make_connector: MakeConnectorFn,
        organization_id: uuid.UUID,
    ) -> None:
        connector = await make_connector()
        await sync_jobs_repo.create(
            _seed_sync_job(
                organization_id=organization_id,
                connector_id=connector.id,
                status=SyncStatus.COMPLETED,
                records_processed=10,
                records_succeeded=10,
                records_failed=0,
            )
        )
        await sync_jobs_repo.create(
            _seed_sync_job(
                organization_id=organization_id,
                connector_id=connector.id,
                status=SyncStatus.FAILED,
                records_processed=5,
                records_succeeded=0,
                records_failed=5,
            )
        )

        worker = StatisticsRollupWorker(db_session_factory, window_seconds=3_600)
        done = await worker.tick()
        assert done == 1

        async with db_session_factory() as fresh:
            latest = await ConnectorStatisticRepository(fresh).latest(organization_id)
            assert latest is not None
            assert latest.syncs_attempted == 2
            assert latest.syncs_succeeded == 1
            assert latest.syncs_failed == 1
            assert latest.records_processed == 15
            assert latest.success_rate == pytest.approx(50.0)

    async def test_tick_rolls_up_multiple_organizations_independently(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        sync_jobs_repo: ConnectorSyncJobRepository,
        connector_service: ConnectorService,
        make_connector: MakeConnectorFn,
        organization_id: uuid.UUID,
    ) -> None:
        other_organization_id = uuid.uuid4()
        connector_a = await make_connector()
        connector_b = await connector_service.register(
            other_organization_id,
            name="other-org-connector",
            category=ConnectorCategory.CUSTOM,
            connector_type="rest_api",
        )

        for _ in range(2):
            await sync_jobs_repo.create(
                _seed_sync_job(
                    organization_id=organization_id,
                    connector_id=connector_a.id,
                    status=SyncStatus.COMPLETED,
                    records_processed=3,
                    records_succeeded=3,
                    records_failed=0,
                )
            )
        await sync_jobs_repo.create(
            _seed_sync_job(
                organization_id=other_organization_id,
                connector_id=connector_b.id,
                status=SyncStatus.FAILED,
                records_processed=1,
                records_succeeded=0,
                records_failed=1,
            )
        )

        worker = StatisticsRollupWorker(db_session_factory, window_seconds=3_600)
        assert await worker.tick() == 2

        async with db_session_factory() as fresh:
            statistics_repo = ConnectorStatisticRepository(fresh)
            latest_a = await statistics_repo.latest(organization_id)
            latest_b = await statistics_repo.latest(other_organization_id)
            assert latest_a is not None
            assert latest_a.syncs_attempted == 2
            assert latest_a.syncs_succeeded == 2
            assert latest_a.success_rate == pytest.approx(100.0)
            assert latest_b is not None
            assert latest_b.syncs_attempted == 1
            assert latest_b.syncs_succeeded == 0
            assert latest_b.syncs_failed == 1
            assert latest_b.success_rate == pytest.approx(0.0)

    async def test_an_organization_with_connectors_but_no_sync_jobs_does_not_appear(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        make_connector: MakeConnectorFn,
        organization_id: uuid.UUID,
    ) -> None:
        # `_organizations()` finds organizations via `SELECT DISTINCT
        # organization_id FROM connector_sync_jobs` -- an organization
        # with a connector but zero *sync jobs* has nothing to roll up,
        # and correctly does not appear.
        await make_connector()

        worker = StatisticsRollupWorker(db_session_factory, window_seconds=3_600)
        assert await worker.tick() == 0

        async with db_session_factory() as fresh:
            latest = await ConnectorStatisticRepository(fresh).latest(organization_id)
            assert latest is None

    async def test_run_job_delegates_to_tick(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        sync_jobs_repo: ConnectorSyncJobRepository,
        make_connector: MakeConnectorFn,
        organization_id: uuid.UUID,
    ) -> None:
        connector = await make_connector()
        await sync_jobs_repo.create(
            _seed_sync_job(
                organization_id=organization_id,
                connector_id=connector.id,
                status=SyncStatus.COMPLETED,
                records_processed=1,
                records_succeeded=1,
                records_failed=0,
            )
        )
        worker = StatisticsRollupWorker(db_session_factory, window_seconds=3_600)
        await worker.run_job(None)  # type: ignore[arg-type]

        async with db_session_factory() as fresh:
            latest = await ConnectorStatisticRepository(fresh).latest(organization_id)
            assert latest is not None

    async def test_a_failure_recomputing_one_organization_does_not_poison_the_next(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        sync_jobs_repo: ConnectorSyncJobRepository,
        connector_service: ConnectorService,
        make_connector: MakeConnectorFn,
        organization_id: uuid.UUID,
    ) -> None:
        other_organization_id = uuid.uuid4()
        connector_a = await make_connector()
        connector_b = await connector_service.register(
            other_organization_id,
            name="other-org-connector-2",
            category=ConnectorCategory.CUSTOM,
            connector_type="rest_api",
        )
        await sync_jobs_repo.create(
            _seed_sync_job(
                organization_id=organization_id,
                connector_id=connector_a.id,
                status=SyncStatus.COMPLETED,
                records_processed=1,
                records_succeeded=1,
                records_failed=0,
            )
        )
        await sync_jobs_repo.create(
            _seed_sync_job(
                organization_id=other_organization_id,
                connector_id=connector_b.id,
                status=SyncStatus.COMPLETED,
                records_processed=1,
                records_succeeded=1,
                records_failed=0,
            )
        )

        # `_organizations()` itself is call #1 and must succeed; a factory
        # that fails on the *first per-organization* recompute (call #2)
        # leaves the second organization's own recompute (call #3)
        # unaffected -- regardless of which organization the database
        # happens to return first.
        flaky = _flaky_after(db_session_factory, fail_on_call=2)
        worker = StatisticsRollupWorker(flaky, window_seconds=3_600)  # type: ignore[arg-type]
        done = await worker.tick()
        assert done == 1

        async with db_session_factory() as fresh:
            statistics_repo = ConnectorStatisticRepository(fresh)
            latest_a = await statistics_repo.latest(organization_id)
            latest_b = await statistics_repo.latest(other_organization_id)
            present = [row for row in (latest_a, latest_b) if row is not None]
            assert len(present) == 1
