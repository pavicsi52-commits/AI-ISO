"""Job registration against a real scheduler, and the remaining gaps.

The registrar test runs against real RabbitMQ and Redis rather than a
stand-in, because the thing worth proving is that this service's job
definitions are ones the framework actually accepts -- and only the
framework can decide that.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
import pytest_asyncio
from shared_core.cache.factory import create_cache_framework
from shared_core.cache.settings import CacheSettings
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.queue.factory import create_queue_framework
from shared_core.scheduler import Job, JobType, SchedulerManager
from shared_core.scheduler import ScheduleType as FrameworkScheduleType
from shared_core.scheduler.factory import create_scheduler_framework
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessments.engine import ControlResult
from app.models.enums import (
    ControlSeverity,
    ExceptionStatus,
    FindingStatus,
    FrameworkKind,
    ResultStatus,
    RiskImpact,
    RiskLikelihood,
    RiskStatus,
)
from app.repositories.governance import ExceptionRepository, RiskRepository
from app.services.assessment import AssessmentService
from app.services.catalogue import CatalogueService
from app.services.finding import FindingService
from app.services.governance import ExceptionService, RiskService
from app.workers.registrar import (
    EXCEPTION_SWEEP_JOB_ID,
    SCORING_ROLLUP_JOB_ID,
    register_exception_sweep,
    register_scoring_rollup,
)
from tests.conftest import MakeControlFn, rabbitmq_test_settings, redis_test_settings, soon


async def _noop(_job: Job) -> None:
    """A job body that does nothing, for registration tests."""


@pytest_asyncio.fixture
async def scheduler() -> AsyncIterator[SchedulerManager]:
    """A real scheduler manager, built the way the factory builds it."""
    queue = await create_queue_framework(rabbitmq_test_settings())
    cache = await create_cache_framework(CacheSettings(redis=redis_test_settings()))
    manager = create_scheduler_framework(
        queue.manager, cache.client, queue_name="compliance_test_queue"
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
        register_scoring_rollup(scheduler, _noop, interval_seconds=900)
        register_exception_sweep(scheduler, _noop, interval_seconds=3_600)

        assert scheduler.registry.get(SCORING_ROLLUP_JOB_ID).job_type is JobType.SYSTEM
        assert scheduler.registry.get(EXCEPTION_SWEEP_JOB_ID).job_type is JobType.SYSTEM
        assert len(scheduler.registry.list_jobs()) == 2

    async def test_a_schedule_carries_its_interval(self, scheduler: SchedulerManager) -> None:
        # A FIXED_RATE schedule without one is accepted by the dataclass
        # and then never fires -- the quietest possible failure for a
        # background job.
        register_scoring_rollup(scheduler, _noop, interval_seconds=900)
        job = scheduler.registry.get(SCORING_ROLLUP_JOB_ID)
        assert job.schedule.schedule_type is FrameworkScheduleType.FIXED_RATE
        assert job.schedule.interval == timedelta(seconds=900)

    async def test_registration_computes_a_first_due_time(
        self, scheduler: SchedulerManager
    ) -> None:
        # Registered but never due is the other silent failure: the job
        # exists, the scheduler polls, nothing ever fires.
        job = register_exception_sweep(scheduler, _noop, interval_seconds=3_600)
        assert job.next_run is not None

    @pytest.mark.parametrize("interval", [0, -1, -600.5])
    async def test_a_non_positive_interval_is_refused(
        self, interval: float, scheduler: SchedulerManager
    ) -> None:
        # Zero would busy-loop the scheduler; negative is meaningless.
        with pytest.raises(ValueError, match="must be positive"):
            register_scoring_rollup(scheduler, _noop, interval_seconds=interval)
        with pytest.raises(ValueError, match="must be positive"):
            register_exception_sweep(scheduler, _noop, interval_seconds=interval)


class TestCatalogueGaps:
    async def test_a_control_cannot_reference_an_unknown_framework(
        self, catalogue_service: CatalogueService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await catalogue_service.create_control(
                organization_id,
                uuid.uuid4(),
                code="X.1",
                title="Orphan",
            )

    async def test_updating_an_unknown_control_is_a_404(
        self, catalogue_service: CatalogueService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await catalogue_service.update_control(organization_id, uuid.uuid4(), title="X")

    async def test_archiving_a_framework_that_has_run_assessments_still_works(
        self,
        catalogue_service: CatalogueService,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # Archiving is a status change, not a deletion -- every result
        # and finding that cites the framework survives it, which is
        # what an assessment's audit trail depends on.
        framework = await make_framework()
        await make_control(framework.id, "1.1")
        planned = await assessment_service.create(
            organization_id, name="Run", framework_id=framework.id
        )
        await assessment_service.run(organization_id, planned.id, targets=[])
        archived = await catalogue_service.archive_framework(organization_id, framework.id)
        assert archived.status == "archived"

    async def test_mapping_needs_both_controls_to_exist(
        self,
        catalogue_service: CatalogueService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        with pytest.raises(NotFoundError):
            await catalogue_service.map_controls(
                organization_id, source_control_id=control.id, target_control_id=uuid.uuid4()
            )

    async def test_frameworks_are_listable_and_paged(
        self, catalogue_service: CatalogueService, organization_id: uuid.UUID
    ) -> None:
        await catalogue_service.create_framework(
            organization_id, slug="ind", name="Industrial", kind=FrameworkKind.INDUSTRIAL
        )
        await catalogue_service.create_framework(organization_id, slug="other", name="Other")
        assert len(await catalogue_service.list_frameworks(organization_id)) == 2
        assert len(await catalogue_service.list_frameworks(organization_id, limit=1)) == 1


class TestAssessmentGaps:
    async def test_running_an_unknown_assessment_is_a_404(
        self, assessment_service: AssessmentService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await assessment_service.run(organization_id, uuid.uuid4(), targets=[])

    async def test_a_catalogue_with_no_automatable_controls_completes_empty(
        self,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # An empty catalogue is a real, if unhelpful, answer -- not a
        # failure. It must complete rather than error, so a caller who
        # forgot to author controls sees a zero-control run and not a
        # stack trace.
        framework = await make_framework()
        planned = await assessment_service.create(
            organization_id, name="Empty", framework_id=framework.id
        )
        finished = await assessment_service.run(organization_id, planned.id, targets=[])
        assert finished.controls_total == 0
        assert finished.score is None or finished.score == 0.0

    async def test_cancelling_a_pending_assessment_works(
        self,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        planned = await assessment_service.create(
            organization_id, name="Never run", framework_id=framework.id
        )
        cancelled = await assessment_service.cancel(organization_id, planned.id)
        assert cancelled.status == "cancelled"


class TestGovernanceGaps:
    async def test_getting_an_unknown_exception_is_a_404(
        self, exception_service: ExceptionService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await exception_service.get(organization_id, uuid.uuid4())

    async def test_getting_an_unknown_risk_is_a_404(
        self, risk_service: RiskService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await risk_service.get(organization_id, uuid.uuid4())

    async def test_an_exception_repository_read_is_tenant_scoped(
        self,
        db_session: AsyncSession,
        exception_service: ExceptionService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        created = await exception_service.request(
            organization_id,
            control_id=control.id,
            title="Scoped",
            business_justification="Reason.",
            expires_at=soon(30),
        )
        with pytest.raises(NotFoundError):
            await ExceptionRepository(db_session).require_in_org(uuid.uuid4(), created.id)
        assert created.status == ExceptionStatus.REQUESTED

    async def test_a_risk_repository_read_is_tenant_scoped(
        self,
        db_session: AsyncSession,
        risk_service: RiskService,
        organization_id: uuid.UUID,
    ) -> None:
        created = await risk_service.register(
            organization_id,
            title="Scoped",
            likelihood=RiskLikelihood.RARE,
            impact=RiskImpact.MINOR,
        )
        with pytest.raises(NotFoundError):
            await RiskRepository(db_session).require_in_org(uuid.uuid4(), created.id)
        assert created.status == RiskStatus.IDENTIFIED

    async def test_rejecting_an_unrequested_exception_is_refused(
        self,
        exception_service: ExceptionService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        created = await exception_service.request(
            organization_id,
            control_id=control.id,
            title="Once",
            business_justification="Reason.",
            expires_at=soon(30),
        )
        await exception_service.approve(organization_id, created.id, approved_by="ciso")
        with pytest.raises(ConflictError):
            await exception_service.reject(organization_id, created.id, reason="Too late.")


class TestFindingGaps:
    async def test_getting_an_unknown_finding_is_a_404(
        self, finding_service: FindingService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await finding_service.get(organization_id, uuid.uuid4())

    async def test_a_finding_can_be_marked_false_positive(
        self,
        finding_service: FindingService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        found, _ = await finding_service.raise_from_result(
            organization_id,
            ControlResult(
                control_id=str(control.id),
                framework_id=None,
                status=ResultStatus.FAIL,
                reason="off",
                target_id="host-1",
                target_type="server",
                severity=ControlSeverity.LOW,
            ),
        )
        closed = await finding_service.transition(
            organization_id,
            found.id,
            target=FindingStatus.FALSE_POSITIVE,
            note="The scanner misread the config.",
        )
        assert closed.status == FindingStatus.FALSE_POSITIVE
        assert closed.resolved_at is not None
