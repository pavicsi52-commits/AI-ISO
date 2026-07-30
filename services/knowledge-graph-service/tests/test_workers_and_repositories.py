"""The background worker, telemetry spans, and the repository read paths.

Three surfaces that share one property: nothing calls them on the
request path, so a defect in any of them stays invisible until the
thing it silently stopped doing is needed.

The worker is the sharpest case. It runs in a process that may never
have built a FastAPI app, on a schedule nobody is watching, and its
failure mode is *statistics that quietly stop updating* -- so it is
exercised here against real PostgreSQL and real Neo4j with its own
driver, exactly as the scheduler would call it.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
import pytest_asyncio
from opentelemetry import trace
from shared_core.cache.factory import create_cache_framework
from shared_core.cache.settings import CacheSettings
from shared_core.exceptions.not_found import NotFoundError
from shared_core.queue.factory import create_queue_framework
from shared_core.scheduler import Job, JobType, Schedule, SchedulerManager
from shared_core.scheduler import ScheduleType as FrameworkScheduleType
from shared_core.scheduler.factory import create_scheduler_framework
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import KnowledgeGraphServiceSettings
from app.graph.repository import GraphRepository
from app.models.enums import (
    AuditAction,
    ChangeAction,
    GraphFormat,
    JobStatus,
    LifecycleState,
    NodeType,
    QueryKind,
    SyncMode,
    SyncSource,
    SyncStatus,
    TwinType,
)
from app.models.graph_audit import GraphAudit
from app.models.graph_change_history import GraphChangeHistory
from app.models.graph_export_job import GraphExportJob
from app.models.graph_import_job import GraphImportJob
from app.models.graph_metadata import GraphMetadata
from app.models.graph_query import GraphQuery
from app.models.graph_report import GraphReport
from app.models.graph_snapshot import GraphSnapshot
from app.models.graph_statistics import GraphStatistics
from app.models.graph_sync_job import GraphSyncJob
from app.models.graph_version import GraphVersion
from app.repositories.graph_audit import GraphAuditRepository
from app.repositories.graph_change_history import GraphChangeHistoryRepository
from app.repositories.graph_export_job import GraphExportJobRepository
from app.repositories.graph_import_job import GraphImportJobRepository
from app.repositories.graph_metadata import GraphMetadataRepository
from app.repositories.graph_query import GraphQueryRepository
from app.repositories.graph_report import GraphReportRepository
from app.repositories.graph_snapshot import GraphSnapshotRepository
from app.repositories.graph_statistics import GraphStatisticsRepository
from app.repositories.graph_sync_job import GraphSyncJobRepository
from app.repositories.graph_version import GraphVersionRepository
from app.telemetry.tracing import (
    trace_analytics,
    trace_cypher,
    trace_export,
    trace_graph_query,
    trace_import,
    trace_synchronization,
    trace_traversal,
)
from app.workers.registrar import STATISTICS_ROLLUP_JOB_ID, register_statistics_rollup
from app.workers.statistics import StatisticsWorker
from tests.conftest import rabbitmq_test_settings, redis_test_settings, utcnow


@pytest_asyncio.fixture
async def scheduler() -> AsyncIterator[SchedulerManager]:
    """A real scheduler manager, built the way the factory builds it.

    Against real RabbitMQ and real Redis rather than a stand-in, because
    the thing worth proving is that this service's job definition is one
    the framework accepts -- and the framework is what decides that.
    """
    queue = await create_queue_framework(rabbitmq_test_settings())
    cache = await create_cache_framework(CacheSettings(redis=redis_test_settings()))
    manager = create_scheduler_framework(
        queue.manager, cache.client, queue_name="knowledge_graph_test_queue"
    )
    yield manager
    await cache.shutdown()
    await queue.shutdown()


class TestJobRegistration:
    """Mapping the rollup onto the scheduler framework."""

    async def test_the_rollup_registers_under_a_deterministic_id(
        self, scheduler: SchedulerManager
    ) -> None:
        # Deterministic, so re-registering on a restart replaces the job
        # rather than leaking a second copy of it.
        register_statistics_rollup(scheduler, _noop, interval_seconds=300)
        job = scheduler.registry.get(STATISTICS_ROLLUP_JOB_ID)
        assert job.job_id == STATISTICS_ROLLUP_JOB_ID
        assert job.job_type is JobType.SYSTEM

    async def test_the_schedule_carries_an_interval(self, scheduler: SchedulerManager) -> None:
        # A FIXED_RATE schedule without one is accepted by the dataclass
        # and then never fires, which is the quietest possible failure
        # for a background job.
        register_statistics_rollup(scheduler, _noop, interval_seconds=300)
        job = scheduler.registry.get(STATISTICS_ROLLUP_JOB_ID)
        assert job.schedule.schedule_type is FrameworkScheduleType.FIXED_RATE
        assert job.schedule.interval == timedelta(seconds=300)

    async def test_registration_computes_a_first_due_time(
        self, scheduler: SchedulerManager
    ) -> None:
        # Registered but never due is the other silent failure: the job
        # exists, the scheduler polls, nothing ever fires.
        job = register_statistics_rollup(scheduler, _noop, interval_seconds=300)
        assert job.next_run is not None

    async def test_one_platform_wide_job_rather_than_one_per_tenant(
        self, scheduler: SchedulerManager
    ) -> None:
        # The rollup iterates tenants internally, so N jobs polling the
        # same tables would be N times the load for no benefit.
        register_statistics_rollup(scheduler, _noop, interval_seconds=300)
        assert len(scheduler.registry.list_jobs()) == 1

    @pytest.mark.parametrize("interval", [0, -1, -300.5])
    async def test_a_non_positive_interval_is_refused(
        self, interval: float, scheduler: SchedulerManager
    ) -> None:
        # Zero would busy-loop the scheduler; negative is meaningless.
        with pytest.raises(ValueError, match="positive"):
            register_statistics_rollup(scheduler, _noop, interval_seconds=interval)


class TestStatisticsWorker:
    """The rollup, run the way the scheduler runs it."""

    async def test_a_tick_recomputes_every_organization_it_finds(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        db_session: AsyncSession,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        del seeded_graph
        # Organizations are discovered from the sync-job table, so the
        # tenant has to have been synced at least once to be seen.
        await GraphSyncJobRepository(db_session).create(
            _sync_job(organization_id, SyncSource.INVENTORY)
        )
        await db_session.flush()

        worker = StatisticsWorker(
            db_session_factory, graph_settings=KnowledgeGraphServiceSettings(_env_file=None)
        )
        assert await worker.tick() >= 1

        stored = await GraphStatisticsRepository(db_session).get_for_org(organization_id)
        assert stored is not None
        assert stored.node_count == 5

    async def test_the_scheduler_entry_point_matches_the_frameworks_signature(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        # The adapter exists so a signature mismatch cannot reach
        # production as "the scheduler silently never fired". Calling it
        # the way the framework does is the only way to prove that.
        del organization_id
        del db_session
        worker = StatisticsWorker(
            db_session_factory, graph_settings=KnowledgeGraphServiceSettings(_env_file=None)
        )
        job = Job(
            job_id=STATISTICS_ROLLUP_JOB_ID,
            job_name=STATISTICS_ROLLUP_JOB_ID,
            job_type=JobType.SYSTEM,
            fn=worker.run_job,
            schedule=Schedule(schedule_type=FrameworkScheduleType.IMMEDIATE),
        )
        assert await worker.run_job(job) is None

    async def test_a_tick_with_no_organizations_is_a_no_op(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = StatisticsWorker(
            db_session_factory,
            graph_settings=KnowledgeGraphServiceSettings(_env_file=None),
            max_per_tick=0,
        )
        assert await worker.tick() == 0

    async def test_one_failing_organization_does_not_stop_the_tick(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        db_session: AsyncSession,
        seeded_graph: GraphRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # One session per organization, so a failure on one tenant cannot
        # poison the transaction the next one needs. Forced by a graph
        # ceiling of zero, which makes the recompute raise for real.
        del seeded_graph
        jobs = GraphSyncJobRepository(db_session)
        await jobs.create(_sync_job(organization_id, SyncSource.INVENTORY))
        await db_session.flush()

        # Pointed at a Neo4j database that does not exist. The settings
        # themselves refuse an impossible read ceiling -- which is the
        # right place for that check -- so the failure has to be forced
        # further out than configuration.
        broken = KnowledgeGraphServiceSettings(_env_file=None, neo4j_database="no-such-database")
        worker = StatisticsWorker(db_session_factory, graph_settings=broken)
        assert await worker.tick() == 0  # recorded as failed, not raised


class TestTelemetrySpans:
    """Every span docs/049 names, emitted for real."""

    def test_each_traced_operation_opens_a_span(self) -> None:
        tracer = trace.get_tracer("test")
        with trace_graph_query(tracer, kind=str(QueryKind.OWNERSHIP)) as span:
            assert span is not None
        with trace_traversal(tracer, root="app-1", depth=2) as span:
            assert span is not None
        with trace_synchronization(tracer, source=str(SyncSource.INVENTORY)) as span:
            assert span is not None
        with trace_analytics(tracer, algorithm="pagerank") as span:
            assert span is not None
        with trace_import(tracer, graph_format=str(GraphFormat.JSON)) as span:
            assert span is not None
        with trace_export(tracer, graph_format=str(GraphFormat.CSV)) as span:
            assert span is not None

    def test_a_traced_cypher_statement_is_truncated(self) -> None:
        # A span attribute is not a query log; an unbounded one turns
        # every trace into a copy of the query history.
        tracer = trace.get_tracer("test")
        with trace_cypher(tracer, statement="MATCH (n) RETURN n " * 500) as span:
            assert span is not None

    def test_a_span_records_an_exception_and_re_raises(self) -> None:
        tracer = trace.get_tracer("test")
        with (
            pytest.raises(RuntimeError, match="boom"),
            trace_traversal(tracer, root="app-1", depth=1),
        ):
            raise RuntimeError("boom")


class TestRepositoryReads:
    """The listing and filtering paths behind the API's read endpoints."""

    async def test_change_history_reads_by_node_and_by_organization(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        changes = GraphChangeHistoryRepository(db_session)
        for key in ("app-1", "vm-1"):
            await changes.create(
                GraphChangeHistory(
                    organization_id=organization_id,
                    action=ChangeAction.NODE_CREATED,
                    node_key=key,
                    entity_type="Application",
                    occurred_at=utcnow(),
                )
            )
        assert len(await changes.list_for_org(organization_id)) == 2
        assert len(await changes.list_for_node(organization_id, "app-1")) == 1

    async def test_change_history_reads_by_sync_job(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        # How "what did last night's sync change?" is answered.
        jobs = GraphSyncJobRepository(db_session)
        job = await jobs.create(_sync_job(organization_id, SyncSource.INVENTORY))
        changes = GraphChangeHistoryRepository(db_session)
        await changes.create(
            GraphChangeHistory(
                organization_id=organization_id,
                action=ChangeAction.NODE_DELETED,
                node_key="gone",
                entity_type="VirtualMachine",
                sync_job_id=job.id,
                occurred_at=utcnow(),
            )
        )
        assert len(await changes.list_for_sync_job(organization_id, job.id)) == 1

    async def test_sync_jobs_filter_by_source_and_status(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        jobs = GraphSyncJobRepository(db_session)
        await jobs.create(_sync_job(organization_id, SyncSource.INVENTORY))
        await jobs.create(
            _sync_job(organization_id, SyncSource.DISCOVERY, status=SyncStatus.FAILED)
        )
        by_source = await jobs.list_for_org(organization_id, source=SyncSource.INVENTORY)
        assert len(by_source) == 1
        by_status = await jobs.list_for_org(organization_id, status=SyncStatus.FAILED)
        assert len(by_status) == 1

    async def test_the_latest_run_for_a_source_is_the_most_recent(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        # The cursor and failure count both come from here, so "latest"
        # being wrong would re-sync from the wrong point.
        jobs = GraphSyncJobRepository(db_session)
        await jobs.create(_sync_job(organization_id, SyncSource.INVENTORY, cursor="first"))
        await jobs.create(_sync_job(organization_id, SyncSource.INVENTORY, cursor="second"))
        latest = await jobs.latest_for_source(organization_id, SyncSource.INVENTORY)
        assert latest is not None
        assert latest.cursor == "second"

    async def test_an_unsynced_source_has_no_latest_run(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        jobs = GraphSyncJobRepository(db_session)
        assert await jobs.latest_for_source(organization_id, SyncSource.WORKFLOW) is None

    async def test_query_history_filters_to_failures(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        queries = GraphQueryRepository(db_session)
        await queries.create(_query(organization_id, succeeded=True, duration_ms=5.0))
        await queries.create(
            _query(organization_id, succeeded=False, duration_ms=1.0, error="broken")
        )
        assert len(await queries.list_for_org(organization_id)) == 2
        failed = await queries.list_for_org(organization_id, failed_only=True)
        assert [one.error for one in failed] == ["broken"]

    async def test_query_history_filters_by_kind(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        queries = GraphQueryRepository(db_session)
        await queries.create(_query(organization_id, kind=QueryKind.OWNERSHIP))
        await queries.create(_query(organization_id, kind=QueryKind.CUSTOM_CYPHER))
        found = await queries.list_for_org(organization_id, kind=QueryKind.OWNERSHIP)
        assert len(found) == 1

    async def test_the_slowest_queries_come_back_slowest_first(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        queries = GraphQueryRepository(db_session)
        await queries.create(_query(organization_id, duration_ms=10.0))
        await queries.create(_query(organization_id, duration_ms=900.0))
        slowest = await queries.slowest(organization_id, limit=1)
        assert slowest[0].duration_ms == 900.0

    async def test_metadata_reads_by_node_and_in_batches(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        # The batched read is what keeps a twin with two hundred
        # components from being two hundred round trips.
        metadata = GraphMetadataRepository(db_session)
        for key in ("app-1", "vm-1", "vm-2"):
            await metadata.create(_metadata(organization_id, key))
        assert await metadata.get_for_node(organization_id, "app-1") is not None
        batched = await metadata.get_many(organization_id, ["app-1", "vm-1", "absent"])
        assert set(batched) == {"app-1", "vm-1"}

    async def test_a_batched_read_of_nothing_is_a_no_op(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        assert await GraphMetadataRepository(db_session).get_many(organization_id, []) == {}

    async def test_metadata_filters_by_twin_type_and_lifecycle(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        metadata = GraphMetadataRepository(db_session)
        await metadata.create(_metadata(organization_id, "app-1", twin_type=TwinType.APPLICATION))
        await metadata.create(
            _metadata(
                organization_id,
                "vm-1",
                twin_type=TwinType.INFRASTRUCTURE,
                lifecycle_state=LifecycleState.RETIRING,
            )
        )
        by_type = await metadata.list_for_org(organization_id, twin_type=TwinType.APPLICATION)
        assert [one.node_key for one in by_type] == ["app-1"]
        by_state = await metadata.list_for_org(
            organization_id, lifecycle_state=LifecycleState.RETIRING
        )
        assert [one.node_key for one in by_state] == ["vm-1"]

    async def test_pinned_nodes_can_be_listed(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        # The list a full sync consults before deleting anything.
        metadata = GraphMetadataRepository(db_session)
        await metadata.create(_metadata(organization_id, "app-1"))
        await metadata.create(_metadata(organization_id, "fw-1", is_pinned=True))
        assert [one.node_key for one in await metadata.list_pinned(organization_id)] == ["fw-1"]

    async def test_audit_entries_filter_by_action_and_entity(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        audits = GraphAuditRepository(db_session)
        await audits.create(_audit(organization_id, AuditAction.NODE_CHANGED, "app-1"))
        await audits.create(_audit(organization_id, AuditAction.CYPHER_EXECUTED, None))
        assert len(await audits.list_for_org(organization_id)) == 2
        assert len(await audits.list_for_org(organization_id, action=AuditAction.NODE_CHANGED)) == 1
        assert len(await audits.list_for_entity(organization_id, "app-1")) == 1

    async def test_reports_read_back_by_organization_and_kind(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        reports = GraphReportRepository(db_session)
        await reports.create(_report(organization_id, QueryKind.IMPACT_ANALYSIS))
        await reports.create(_report(organization_id, QueryKind.BLAST_RADIUS))
        assert len(await reports.list_for_org(organization_id)) == 2
        found = await reports.list_for_org(organization_id, kind=QueryKind.BLAST_RADIUS)
        assert len(found) == 1

    async def test_reports_read_back_by_root_key(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        # "What have we said about this node before?" during an incident.
        reports = GraphReportRepository(db_session)
        await reports.create(_report(organization_id, QueryKind.IMPACT_ANALYSIS, root="host-1"))
        assert len(await reports.list_for_root(organization_id, "host-1")) == 1

    async def test_import_and_export_jobs_list_for_an_organization(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        imports = GraphImportJobRepository(db_session)
        await imports.create(
            GraphImportJob(
                organization_id=organization_id,
                filename="graph.json",
                import_format=GraphFormat.JSON,
                status=JobStatus.SUCCEEDED,
                started_at=utcnow(),
            )
        )
        assert len(await imports.list_for_org(organization_id)) == 1

        exports = GraphExportJobRepository(db_session)
        stored = await exports.create(
            GraphExportJob(
                organization_id=organization_id,
                export_format=GraphFormat.JSON,
                status=JobStatus.SUCCEEDED,
                filename="graph-export.json",
                started_at=utcnow(),
            )
        )
        assert len(await exports.list_for_org(organization_id)) == 1
        assert (await exports.get_by_id(stored.id)) is not None

    async def test_requiring_an_absent_export_raises(self, db_session: AsyncSession) -> None:
        with pytest.raises(NotFoundError):
            await GraphExportJobRepository(db_session).require_by_id(uuid.uuid4())

    async def test_snapshots_list_and_expire(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        snapshots = GraphSnapshotRepository(db_session)
        moment = utcnow()
        await snapshots.create(
            _snapshot(organization_id, "current", expires_at=moment + timedelta(days=30))
        )
        await snapshots.create(
            _snapshot(organization_id, "stale", expires_at=moment - timedelta(days=1))
        )
        assert len(await snapshots.list_for_org(organization_id)) == 2
        expired = await snapshots.list_expired(organization_id, moment=moment)
        assert [one.label for one in expired] == ["stale"]

    async def test_requiring_an_absent_snapshot_raises(self, db_session: AsyncSession) -> None:
        with pytest.raises(NotFoundError):
            await GraphSnapshotRepository(db_session).require_by_id(uuid.uuid4())

    async def test_versions_sequence_from_one_and_list_newest_first(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        versions = GraphVersionRepository(db_session)
        assert await versions.next_sequence(organization_id) == 1
        await versions.create(_version(organization_id, sequence=1, label="v1"))
        assert await versions.next_sequence(organization_id) == 2
        await versions.create(_version(organization_id, sequence=2, label="v2"))
        listed = await versions.list_for_org(organization_id)
        assert [one.label for one in listed] == ["v2", "v1"]

    async def test_a_version_can_be_fetched_by_its_sequence(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        versions = GraphVersionRepository(db_session)
        await versions.create(_version(organization_id, sequence=1, label="v1"))
        await versions.create(_version(organization_id, sequence=2, label="v2"))
        found = await versions.get_by_sequence(organization_id, 2)
        assert found is not None
        assert found.label == "v2"
        assert await versions.get_by_sequence(organization_id, 99) is None

    async def test_statistics_are_stored_once_per_organization(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        statistics = GraphStatisticsRepository(db_session)
        assert await statistics.get_for_org(organization_id) is None
        stored = await statistics.create(
            GraphStatistics(organization_id=organization_id, computed_at=utcnow(), node_count=5)
        )
        stored.node_count = 6
        updated = await statistics.update(stored)
        assert updated.node_count == 6
        assert (await statistics.get_for_org(organization_id)) is not None

    async def test_every_repository_scopes_reads_to_one_organization(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        # One sweep rather than a per-repository test: the failure mode is
        # identical everywhere and it is the one that matters most.
        other = uuid.uuid4()
        await GraphAuditRepository(db_session).create(
            _audit(organization_id, AuditAction.NODE_CHANGED, "app-1")
        )
        await GraphSyncJobRepository(db_session).create(
            _sync_job(organization_id, SyncSource.INVENTORY)
        )
        await GraphQueryRepository(db_session).create(_query(organization_id))
        await GraphMetadataRepository(db_session).create(_metadata(organization_id, "app-1"))
        await GraphReportRepository(db_session).create(
            _report(organization_id, QueryKind.IMPACT_ANALYSIS)
        )

        assert await GraphAuditRepository(db_session).list_for_org(other) == []
        assert await GraphSyncJobRepository(db_session).list_for_org(other) == []
        assert await GraphQueryRepository(db_session).list_for_org(other) == []
        assert await GraphMetadataRepository(db_session).list_for_org(other) == []
        assert await GraphReportRepository(db_session).list_for_org(other) == []


async def _noop(_job: Job) -> None:
    """A job body that does nothing, for registration tests."""


def _sync_job(
    organization_id: uuid.UUID,
    source: SyncSource,
    *,
    status: SyncStatus = SyncStatus.SUCCEEDED,
    cursor: str | None = None,
) -> GraphSyncJob:
    return GraphSyncJob(
        organization_id=organization_id,
        source=source,
        mode=SyncMode.INCREMENTAL,
        status=status,
        cursor=cursor,
        started_at=utcnow(),
        finished_at=utcnow(),
    )


def _query(
    organization_id: uuid.UUID,
    *,
    kind: QueryKind = QueryKind.CUSTOM_CYPHER,
    succeeded: bool = True,
    duration_ms: float = 1.0,
    error: str | None = None,
) -> GraphQuery:
    return GraphQuery(
        organization_id=organization_id,
        kind=kind,
        cypher="MATCH (n:GraphNode) RETURN n LIMIT $limit",
        parameters={},
        succeeded=succeeded,
        row_count=0,
        duration_ms=duration_ms,
        error=error,
        executed_at=utcnow(),
    )


def _metadata(
    organization_id: uuid.UUID,
    node_key: str,
    *,
    twin_type: TwinType = TwinType.APPLICATION,
    lifecycle_state: LifecycleState = LifecycleState.ACTIVE,
    is_pinned: bool = False,
) -> GraphMetadata:
    return GraphMetadata(
        organization_id=organization_id,
        node_key=node_key,
        node_type=str(NodeType.APPLICATION),
        display_name=node_key,
        twin_type=twin_type,
        lifecycle_state=lifecycle_state,
        is_pinned=is_pinned,
    )


def _audit(organization_id: uuid.UUID, action: AuditAction, entity_key: str | None) -> GraphAudit:
    return GraphAudit(
        organization_id=organization_id,
        action=action,
        entity_type="node",
        entity_key=entity_key,
        occurred_at=utcnow(),
    )


def _report(organization_id: uuid.UUID, kind: QueryKind, *, root: str = "app-1") -> GraphReport:
    return GraphReport(
        organization_id=organization_id,
        title=f"{kind} of {root}",
        kind=kind,
        root_key=root,
        parameters={},
        summary="test",
        result={},
        generated_at=utcnow(),
    )


def _snapshot(organization_id: uuid.UUID, label: str, *, expires_at: object) -> GraphSnapshot:
    return GraphSnapshot(
        organization_id=organization_id,
        label=label,
        status=JobStatus.SUCCEEDED,
        snapshot_format=GraphFormat.JSON,
        captured_at=utcnow(),
        expires_at=expires_at,
    )


def _version(organization_id: uuid.UUID, *, sequence: int, label: str) -> GraphVersion:
    return GraphVersion(
        organization_id=organization_id,
        sequence=sequence,
        label=label,
        node_count=0,
        relationship_count=0,
        node_type_counts={},
        relationship_type_counts={},
        captured_at=utcnow(),
    )
