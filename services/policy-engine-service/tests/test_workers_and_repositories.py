"""The background workers, telemetry spans, and repository read paths.

Three surfaces that share one property: nothing calls them on the request
path, so a defect in any of them stays invisible until the thing it
silently stopped doing is needed.

The workers are the sharpest case. Each keeps a table honest on a
schedule nobody is watching, and each one's failure mode is silence --
approvals that never expire, quota periods that never roll, decisions
that grow without bound.
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

from app.attributes.resolver import EvaluationContext
from app.config.settings import PolicyEngineServiceSettings
from app.models.decision import PolicyDecision
from app.models.enums import (
    ActionType,
    ApprovalStatus,
    ApprovalType,
    AttributeSource,
    AuditAction,
    ComplianceStandard,
    PolicyCategory,
    PolicyEffect,
    PolicyStatus,
    QuotaPeriod,
    QuotaScope,
    ReportKind,
    ResourceType,
    SubjectType,
    ViolationStatus,
)
from app.models.policy import PolicyCategoryRecord
from app.models.rule import PolicyAttribute
from app.repositories.policy import (
    PolicyAttributeRepository,
    PolicyCategoryRepository,
    PolicyRepository,
    PolicyVersionRepository,
)
from app.repositories.runtime import (
    PolicyApprovalRepository,
    PolicyAuditRepository,
    PolicyDecisionRepository,
    PolicyQuotaRepository,
    PolicyReportRepository,
    PolicyViolationRepository,
)
from app.services.approval import ApprovalService
from app.services.compliance import ComplianceService
from app.services.decision import DecisionRequest, DecisionService
from app.services.quota import QuotaService
from app.telemetry.tracing import (
    trace_approval,
    trace_decision_generation,
    trace_evaluation,
    trace_publish,
    trace_quota_evaluation,
    trace_rule_matching,
    trace_simulation,
)
from app.workers.maintenance import MaintenanceWorker
from app.workers.registrar import (
    APPROVAL_SWEEP_JOB_ID,
    STATISTICS_ROLLUP_JOB_ID,
    register_approval_sweep,
    register_statistics_rollup,
)
from app.workers.statistics import StatisticsWorker
from tests.conftest import (
    PublishedPolicyFn,
    rabbitmq_test_settings,
    redis_test_settings,
    utcnow,
)


async def _noop(_job: Job) -> None:
    """A job body that does nothing, for registration tests."""


@pytest_asyncio.fixture
async def scheduler() -> AsyncIterator[SchedulerManager]:
    """A real scheduler manager, built the way the factory builds it.

    Against real RabbitMQ and real Redis rather than a stand-in, because
    the thing worth proving is that this service's job definitions are
    ones the framework accepts -- and the framework decides that.
    """
    queue = await create_queue_framework(rabbitmq_test_settings())
    cache = await create_cache_framework(CacheSettings(redis=redis_test_settings()))
    manager = create_scheduler_framework(
        queue.manager, cache.client, queue_name="policy_engine_test_queue"
    )
    yield manager
    await cache.shutdown()
    await queue.shutdown()


class TestJobRegistration:
    """Mapping this service's jobs onto the scheduler framework."""

    async def test_both_jobs_register_under_deterministic_ids(
        self, scheduler: SchedulerManager
    ) -> None:
        # Deterministic, so re-registering on a restart replaces the job
        # rather than leaking a second copy of it.
        register_statistics_rollup(scheduler, _noop, interval_seconds=900)
        register_approval_sweep(scheduler, _noop, interval_seconds=600)

        assert scheduler.registry.get(STATISTICS_ROLLUP_JOB_ID).job_type is JobType.SYSTEM
        assert scheduler.registry.get(APPROVAL_SWEEP_JOB_ID).job_type is JobType.SYSTEM
        assert len(scheduler.registry.list_jobs()) == 2

    async def test_a_schedule_carries_its_interval(self, scheduler: SchedulerManager) -> None:
        # A FIXED_RATE schedule without one is accepted by the dataclass
        # and then never fires, which is the quietest possible failure for
        # a background job.
        register_statistics_rollup(scheduler, _noop, interval_seconds=900)
        job = scheduler.registry.get(STATISTICS_ROLLUP_JOB_ID)
        assert job.schedule.schedule_type is FrameworkScheduleType.FIXED_RATE
        assert job.schedule.interval == timedelta(seconds=900)

    async def test_registration_computes_a_first_due_time(
        self, scheduler: SchedulerManager
    ) -> None:
        # Registered but never due is the other silent failure: the job
        # exists, the scheduler polls, nothing ever fires.
        job = register_approval_sweep(scheduler, _noop, interval_seconds=600)
        assert job.next_run is not None

    @pytest.mark.parametrize("interval", [0, -1, -600.5])
    async def test_a_non_positive_interval_is_refused(
        self, interval: float, scheduler: SchedulerManager
    ) -> None:
        # Zero would busy-loop the scheduler; negative is meaningless.
        with pytest.raises(ValueError, match="must be positive"):
            register_statistics_rollup(scheduler, _noop, interval_seconds=interval)
        with pytest.raises(ValueError, match="must be positive"):
            register_approval_sweep(scheduler, _noop, interval_seconds=interval)


class TestStatisticsWorker:
    """The rollup, run the way the scheduler runs it."""

    async def test_a_tick_recomputes_every_organization_it_finds(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        db_session: AsyncSession,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # Organizations are discovered from the policy catalogue rather
        # than the decision log: one that has authored governance but not
        # yet exercised it still wants a rollup.
        await make_policy("p1", PolicyEffect.DENY)
        await db_session.flush()

        worker = StatisticsWorker(db_session_factory)
        assert await worker.tick() >= 1

    async def test_the_scheduler_entry_point_matches_the_frameworks_signature(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        # The adapter exists so a signature mismatch cannot reach
        # production as "the scheduler silently never fired".
        worker = StatisticsWorker(db_session_factory)
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
        worker = StatisticsWorker(db_session_factory, max_per_tick=0)
        assert await worker.tick() == 0


class TestMaintenanceWorker:
    """Expiring approvals, rolling periods, enforcing retention."""

    def _settings(self, **overrides: object) -> PolicyEngineServiceSettings:
        return PolicyEngineServiceSettings(_env_file=None, **overrides)  # type: ignore[arg-type]

    async def test_the_scheduler_entry_point_matches_the_frameworks_signature(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = MaintenanceWorker(db_session_factory, graph_settings=self._settings())
        job = Job(
            job_id=APPROVAL_SWEEP_JOB_ID,
            job_name=APPROVAL_SWEEP_JOB_ID,
            job_type=JobType.SYSTEM,
            fn=worker.run_job,
            schedule=Schedule(schedule_type=FrameworkScheduleType.IMMEDIATE),
        )
        assert await worker.run_job(job) is None

    async def test_a_sweep_expires_an_overdue_approval(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        db_session: AsyncSession,
        approval_service: ApprovalService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # A pending approval that can never complete, sitting on somebody's
        # list forever, is how a queue stops being read at all.
        await make_policy("p1", PolicyEffect.DENY)
        raised = await approval_service.raise_for_decision(
            organization_id,
            policy_id=None,
            decision_id=None,
            subject_type=SubjectType.USER,
            subject_id="user-1",
            resource_type=ResourceType.DASHBOARD,
            resource_id=None,
            action=ActionType.READ,
            obligations={"approval_type": "single"},
        )
        raised.expires_at = utcnow() - timedelta(hours=2)
        await db_session.flush()

        worker = MaintenanceWorker(db_session_factory, graph_settings=self._settings())
        totals = await worker.tick()
        assert totals["expired_approvals"] >= 1

        # Refreshed rather than re-read through the service: the sweep
        # updated the row in the worker's own session, so this session's
        # identity map still holds the pre-sweep instance.
        await db_session.refresh(raised)
        assert str(raised.status) == str(ApprovalStatus.EXPIRED)

    async def test_a_sweep_rolls_a_stale_quota_period(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        db_session: AsyncSession,
        quota_service: QuotaService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # A quota whose period ended keeps reporting last month's usage,
        # so every figure derived from it is wrong until something touches
        # it. The sweep is the backstop for budgets nothing has read.
        await make_policy("p1", PolicyEffect.DENY)
        quota = await quota_service.define(
            organization_id,
            scope=QuotaScope.ORGANIZATION,
            scope_id=str(organization_id),
            resource="requests",
            limit_value=10,
            period=QuotaPeriod.DAILY,
        )
        quota.consumed = 10.0
        quota.period_started_at = utcnow() - timedelta(days=5)
        await db_session.flush()

        worker = MaintenanceWorker(db_session_factory, graph_settings=self._settings())
        totals = await worker.tick()
        assert totals["rolled_quotas"] >= 1

    async def test_a_sweep_enforces_decision_retention(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        db_session: AsyncSession,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # The only thing that removes them; without it the table grows
        # without bound.
        await make_policy("p1", PolicyEffect.DENY)
        await PolicyDecisionRepository(db_session).create(
            PolicyDecision(
                organization_id=organization_id,
                subject_type=SubjectType.USER,
                subject_id="user-1",
                resource_type=ResourceType.DASHBOARD,
                action=ActionType.READ,
                effect=PolicyEffect.DENY,
                permitted=False,
                reason="old",
                decided_at=utcnow() - timedelta(days=400),
            )
        )
        await db_session.flush()

        worker = MaintenanceWorker(
            db_session_factory, graph_settings=self._settings(decision_retention_days=90)
        )
        totals = await worker.tick()
        assert totals["purged_decisions"] >= 1

    async def test_a_sweep_with_no_organizations_is_a_no_op(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = MaintenanceWorker(
            db_session_factory, graph_settings=self._settings(), max_per_tick=0
        )
        assert await worker.tick() == {
            "expired_approvals": 0,
            "rolled_quotas": 0,
            "purged_decisions": 0,
        }


class TestTelemetrySpans:
    """Every span docs/050 names, emitted for real."""

    def test_each_traced_operation_opens_a_span(self) -> None:
        tracer = trace.get_tracer("test")
        with trace_evaluation(
            tracer, resource_type=str(ResourceType.SECRET), action=str(ActionType.DELETE)
        ) as span:
            assert span is not None
        with trace_rule_matching(tracer, policy_slug="p1", conditions=3) as span:
            assert span is not None
        with trace_decision_generation(tracer, effect="deny", matched=2) as span:
            assert span is not None
        with trace_simulation(tracer, label="what-if", requests=10) as span:
            assert span is not None
        with trace_approval(tracer, approval_type=str(ApprovalType.SINGLE)) as span:
            assert span is not None
        with trace_quota_evaluation(tracer, resource="api_calls") as span:
            assert span is not None
        with trace_publish(tracer, policy_slug="p1", version="1.0.1") as span:
            assert span is not None

    def test_a_span_records_an_exception_and_re_raises(self) -> None:
        tracer = trace.get_tracer("test")
        with (
            pytest.raises(RuntimeError, match="boom"),
            trace_evaluation(tracer, resource_type="dashboard", action="read"),
        ):
            raise RuntimeError("boom")


class TestPolicyRepositoryReads:
    """The listing and filtering paths behind the read endpoints."""

    async def test_a_policy_is_findable_by_slug(
        self,
        db_session: AsyncSession,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("findme", PolicyEffect.DENY)
        repository = PolicyRepository(db_session)
        assert (await repository.get_by_slug(organization_id, "findme")) is not None
        assert (await repository.require_by_slug(organization_id, "findme")).slug == "findme"

    async def test_an_unknown_slug_raises(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError, match="No policy with slug"):
            await PolicyRepository(db_session).require_by_slug(organization_id, "ghost")

    async def test_a_slug_lookup_does_not_cross_tenants(
        self,
        db_session: AsyncSession,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # A slug is a human-chosen name, so an unscoped lookup lets one
        # tenant read another's governance by guessing one.
        await make_policy("deny-secret-export", PolicyEffect.DENY)
        assert (
            await PolicyRepository(db_session).get_by_slug(uuid.uuid4(), "deny-secret-export")
        ) is None

    async def test_policies_filter_by_status_and_category(
        self,
        db_session: AsyncSession,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("published", PolicyEffect.DENY)
        await make_policy("drafted", PolicyEffect.ALLOW, publish=False)
        repository = PolicyRepository(db_session)

        published = await repository.list_for_org(organization_id, status=PolicyStatus.PUBLISHED)
        assert [one.slug for one in published] == ["published"]

        by_category = await repository.list_for_org(
            organization_id, category=PolicyCategory.AUTHORIZATION
        )
        assert len(by_category) == 2

    async def test_policies_paginate(
        self,
        db_session: AsyncSession,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        for index in range(3):
            await make_policy(f"p{index}", PolicyEffect.DENY, publish=False)
        repository = PolicyRepository(db_session)
        first = await repository.list_for_org(organization_id, limit=2, offset=0)
        second = await repository.list_for_org(organization_id, limit=2, offset=2)
        assert len(first) == 2
        assert len(second) == 1

    async def test_named_policies_do_not_cross_tenants(
        self,
        db_session: AsyncSession,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # Scoped even though ids are unguessable: obscurity is not
        # authorization, and a forwarded id should not become a read of
        # another tenant's governance.
        published = await make_policy("p1", PolicyEffect.DENY)
        repository = PolicyRepository(db_session)
        assert await repository.list_by_ids(organization_id, [published.id])
        assert await repository.list_by_ids(uuid.uuid4(), [published.id]) == []
        assert await repository.list_by_ids(organization_id, []) == []

    async def test_versions_read_back_by_number_and_sequence(
        self,
        db_session: AsyncSession,
        policy_service: object,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        published = await make_policy("p1", PolicyEffect.DENY)
        repository = PolicyVersionRepository(db_session)

        latest = await repository.latest_for_policy(organization_id, published.id)
        assert latest is not None
        found = await repository.get_by_version(
            organization_id, published.id, latest.semantic_version
        )
        assert found is not None
        assert await repository.next_sequence(organization_id, published.id) == 2

    async def test_an_unknown_version_is_none(
        self,
        db_session: AsyncSession,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        published = await make_policy("p1", PolicyEffect.DENY)
        assert (
            await PolicyVersionRepository(db_session).get_by_version(
                organization_id, published.id, "9.9.9"
            )
        ) is None

    async def test_the_attribute_catalogue_reports_its_sensitive_paths(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        repository = PolicyAttributeRepository(db_session)
        await repository.create(
            PolicyAttribute(
                organization_id=organization_id,
                source=AttributeSource.CONTEXT,
                path="token",
                name="Token",
                is_sensitive=True,
            )
        )
        await repository.create(
            PolicyAttribute(
                organization_id=organization_id,
                source=AttributeSource.SUBJECT,
                path="department",
                name="Department",
            )
        )
        assert len(await repository.list_for_org(organization_id)) == 2
        assert await repository.sensitive_paths(organization_id) == {("context", "token")}

    async def test_categories_read_back(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        repository = PolicyCategoryRepository(db_session)
        await repository.create(
            PolicyCategoryRecord(organization_id=organization_id, slug="ours", name="Ours")
        )
        assert [one.slug for one in await repository.list_for_org(organization_id)] == ["ours"]
        assert (await repository.get_by_slug(organization_id, "ours")) is not None
        assert (await repository.get_by_slug(organization_id, "nope")) is None


class TestRuntimeRepositoryReads:
    """Decisions, violations, approvals, quotas, reports, audit."""

    async def test_decisions_filter_and_aggregate(
        self,
        db_session: AsyncSession,
        decision_service: DecisionService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("deny-platform", PolicyEffect.DENY)
        await decision_service.decide(
            DecisionRequest(
                organization_id=organization_id,
                subject_type=SubjectType.USER,
                subject_id="user-1",
                resource_type=ResourceType.DASHBOARD,
                action=ActionType.READ,
                context=EvaluationContext(subject={"department": "platform"}),
            )
        )
        await db_session.flush()
        repository = PolicyDecisionRepository(db_session)

        assert len(await repository.list_for_org(organization_id, denied_only=True)) == 1
        assert len(await repository.list_for_org(organization_id, subject_id="user-1")) == 1
        assert await repository.list_for_org(organization_id, effect=PolicyEffect.ALLOW) == []

        stats = await repository.statistics_for_org(organization_id)
        assert stats["total"] == 1
        assert stats["denied"] == 1
        assert await repository.percentile_latency(organization_id) >= 0.0
        assert await repository.counts_by_effect(organization_id) == {"deny": 1}

    async def test_violations_filter_by_status_and_severity(
        self,
        db_session: AsyncSession,
        compliance_service: ComplianceService,
        organization_id: uuid.UUID,
    ) -> None:
        await compliance_service.record_violation(
            organization_id,
            title="high one",
            standard=ComplianceStandard.SECURITY,
            severity="high",
        )
        await compliance_service.record_violation(
            organization_id,
            title="low one",
            standard=ComplianceStandard.NAMING,
            severity="low",
        )
        repository = PolicyViolationRepository(db_session)

        assert len(await repository.list_for_org(organization_id, severity="high")) == 1
        assert len(await repository.list_for_org(organization_id, status=ViolationStatus.OPEN)) == 2
        assert await repository.count_open(organization_id) == 2

    async def test_requiring_an_absent_violation_raises(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await PolicyViolationRepository(db_session).require_in_org(
                organization_id, uuid.uuid4()
            )

    async def test_approvals_filter_and_count(
        self,
        db_session: AsyncSession,
        approval_service: ApprovalService,
        organization_id: uuid.UUID,
    ) -> None:
        await approval_service.raise_for_decision(
            organization_id,
            policy_id=None,
            decision_id=None,
            subject_type=SubjectType.USER,
            subject_id="user-1",
            resource_type=ResourceType.DASHBOARD,
            resource_id=None,
            action=ActionType.READ,
            obligations={"approval_type": "single"},
        )
        repository = PolicyApprovalRepository(db_session)

        assert (
            len(await repository.list_for_org(organization_id, status=ApprovalStatus.PENDING)) == 1
        )
        assert len(await repository.list_for_org(organization_id, subject_id="user-1")) == 1
        assert await repository.count_pending(organization_id) == 1

    async def test_requiring_an_absent_approval_raises(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await PolicyApprovalRepository(db_session).require_in_org(organization_id, uuid.uuid4())

    async def test_quotas_read_back_by_their_natural_key(
        self,
        db_session: AsyncSession,
        quota_service: QuotaService,
        organization_id: uuid.UUID,
    ) -> None:
        await quota_service.define(
            organization_id,
            scope=QuotaScope.PROJECT,
            scope_id="proj-1",
            resource="reports",
            limit_value=5,
        )
        repository = PolicyQuotaRepository(db_session)

        found = await repository.get_one(
            organization_id, scope=QuotaScope.PROJECT, scope_id="proj-1", resource="reports"
        )
        assert found is not None
        assert (
            await repository.get_one(
                organization_id,
                scope=QuotaScope.PROJECT,
                scope_id="other",
                resource="reports",
            )
        ) is None

    async def test_applicable_quotas_cover_every_scope_a_request_sits_in(
        self,
        db_session: AsyncSession,
        quota_service: QuotaService,
        organization_id: uuid.UUID,
    ) -> None:
        # Returning only the narrowest would let a user inside their
        # personal limit blow through the organization's.
        await quota_service.define(
            organization_id,
            scope=QuotaScope.ORGANIZATION,
            scope_id=str(organization_id),
            resource="requests",
            limit_value=100,
        )
        await quota_service.define(
            organization_id,
            scope=QuotaScope.USER,
            scope_id="user-1",
            resource="requests",
            limit_value=10,
        )
        found = await PolicyQuotaRepository(db_session).list_applicable(
            organization_id,
            scopes=[
                (QuotaScope.ORGANIZATION, str(organization_id)),
                (QuotaScope.USER, "user-1"),
            ],
            resource="requests",
        )
        assert len(found) == 2

    async def test_no_scopes_matches_nothing(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        assert (
            await PolicyQuotaRepository(db_session).list_applicable(organization_id, scopes=[])
            == []
        )

    async def test_a_quota_records_that_it_blocked_something(
        self,
        db_session: AsyncSession,
        quota_service: QuotaService,
        organization_id: uuid.UUID,
    ) -> None:
        quota = await quota_service.define(
            organization_id,
            scope=QuotaScope.ORGANIZATION,
            scope_id=str(organization_id),
            resource="requests",
            limit_value=1,
        )
        repository = PolicyQuotaRepository(db_session)
        await repository.record_exceeded(quota.id, moment=utcnow())
        await db_session.flush()
        await db_session.refresh(quota)
        assert quota.exceeded_count == 1
        assert quota.exceeded_at is not None

    async def test_reports_filter_by_kind(
        self,
        db_session: AsyncSession,
        report_service: object,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("p1", PolicyEffect.DENY)
        await report_service.generate(organization_id, kind=ReportKind.POLICY)  # type: ignore[attr-defined]
        await report_service.generate(organization_id, kind=ReportKind.VIOLATION)  # type: ignore[attr-defined]
        repository = PolicyReportRepository(db_session)

        assert len(await repository.list_for_org(organization_id)) == 2
        assert len(await repository.list_for_org(organization_id, kind=ReportKind.POLICY)) == 1

    async def test_requiring_an_absent_report_raises(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await PolicyReportRepository(db_session).require_in_org(organization_id, uuid.uuid4())

    async def test_audit_entries_filter_by_action_and_entity(
        self, db_session: AsyncSession, audit_service: object, organization_id: uuid.UUID
    ) -> None:
        await audit_service.record(  # type: ignore[attr-defined]
            organization_id=organization_id,
            action=AuditAction.POLICY_CHANGED,
            entity_type="policy",
            entity_id="p1",
        )
        await audit_service.record(  # type: ignore[attr-defined]
            organization_id=organization_id,
            action=AuditAction.DECISION_MADE,
            entity_type="decision",
        )
        repository = PolicyAuditRepository(db_session)

        assert len(await repository.list_for_org(organization_id)) == 2
        assert (
            len(await repository.list_for_org(organization_id, action=AuditAction.POLICY_CHANGED))
            == 1
        )
        assert len(await repository.list_for_entity(organization_id, "p1")) == 1
