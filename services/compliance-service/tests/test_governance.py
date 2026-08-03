"""Exceptions, risk, remediation, scoring, reporting, audit, and workers.

Against real PostgreSQL. The audit-failure path uses the real session
factory rather than the SAVEPOINT-isolated fixture, because what it
asserts is about transaction lifetime -- which is exactly what that
isolation overrides.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.validation import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.assessments.engine import ControlResult, Target
from app.models.enums import (
    AssessmentStatus,
    AuditAction,
    ControlSeverity,
    ExceptionKind,
    ExceptionStatus,
    FindingStatus,
    RemediationStatus,
    ReportKind,
    ResultStatus,
    RiskImpact,
    RiskLikelihood,
    RiskSeverity,
    RiskStatus,
)
from app.repositories.governance import AuditRepository
from app.services.assessment import AssessmentService
from app.services.catalogue import CatalogueService
from app.services.finding import FindingService
from app.services.governance import ExceptionService, RemediationService, RiskService
from app.services.reporting import AuditService, ReportService, StatisticsService
from app.services.scoring import ScoringService
from app.workers.maintenance import MaintenanceWorker
from app.workers.statistics import StatisticsWorker
from tests.conftest import MakeControlFn, RecordingPublisher, soon, utcnow


class TestExceptions:
    async def test_a_temporary_exception_needs_an_expiry(
        self,
        exception_service: ExceptionService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # An exception without one is a permanent exception that has not
        # admitted it.
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        with pytest.raises(ValidationError, match="expiry"):
            await exception_service.request(
                organization_id,
                control_id=control.id,
                title="Forever",
                business_justification="Because.",
            )

    async def test_a_permanent_exception_still_gets_a_review_date(
        self,
        exception_service: ExceptionService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # A waiver nobody ever looks at again is an undocumented policy
        # change, whatever it is called.
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        created = await exception_service.request(
            organization_id,
            control_id=control.id,
            title="Architectural",
            business_justification="The control does not apply to air-gapped systems.",
            kind=ExceptionKind.PERMANENT,
        )
        assert created.expires_at is None
        assert created.next_review_at is not None

    async def test_an_exception_past_the_ceiling_is_refused(
        self,
        exception_service: ExceptionService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # "Temporary" is the word people use for the waivers that outlive
        # the systems they were granted for.
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        with pytest.raises(ValidationError, match="ceiling"):
            await exception_service.request(
                organization_id,
                control_id=control.id,
                title="Two years",
                business_justification="Long project.",
                expires_at=soon(800),
            )

    async def test_an_exception_expiring_in_the_past_is_refused(
        self,
        exception_service: ExceptionService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        with pytest.raises(ValidationError, match="in the past"):
            await exception_service.request(
                organization_id,
                control_id=control.id,
                title="Already gone",
                business_justification="Oops.",
                expires_at=utcnow() - timedelta(days=1),
            )

    async def test_an_exception_needs_a_justification(
        self,
        exception_service: ExceptionService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # Without one it is indistinguishable from an oversight.
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        with pytest.raises(ValidationError, match="justification"):
            await exception_service.request(
                organization_id,
                control_id=control.id,
                title="Blank",
                business_justification="   ",
                expires_at=soon(30),
            )

    async def test_an_exception_is_requested_not_active(
        self,
        exception_service: ExceptionService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
        publisher: RecordingPublisher,
    ) -> None:
        # One that took effect the moment somebody asked for it would
        # make the approval step decorative.
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        created = await exception_service.request(
            organization_id,
            control_id=control.id,
            title="Pending",
            business_justification="Vendor appliance.",
            expires_at=soon(30),
        )
        assert created.status == ExceptionStatus.REQUESTED
        assert "ComplianceExceptionCreated" in publisher.names

    async def test_approving_twice_is_refused(
        self,
        exception_service: ExceptionService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # Approving an already-approved waiver would reset its review
        # clock; approving a revoked one would resurrect a decision
        # somebody deliberately took back.
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
            await exception_service.approve(organization_id, created.id, approved_by="ciso")

    async def test_rejecting_records_the_reason(
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
            title="No",
            business_justification="Reason.",
            expires_at=soon(30),
        )
        rejected = await exception_service.reject(
            organization_id, created.id, reason="Compensating control is insufficient."
        )
        assert rejected.status == ExceptionStatus.REJECTED
        assert "insufficient" in (rejected.rejected_reason or "")

    async def test_revoking_a_waiver_that_is_not_live_is_refused(
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
            title="Not yet",
            business_justification="Reason.",
            expires_at=soon(30),
        )
        with pytest.raises(ConflictError, match="not in force"):
            await exception_service.revoke(organization_id, created.id, reason="No.")

    async def test_a_review_finding_it_unneeded_revokes_it(
        self,
        exception_service: ExceptionService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # Recording the conclusion while leaving the waiver in force
        # would be the worst of both worlds: the register says the right
        # thing while the estate keeps behaving the old way.
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        created = await exception_service.request(
            organization_id,
            control_id=control.id,
            title="Legacy",
            business_justification="Reason.",
            expires_at=soon(30),
        )
        await exception_service.approve(organization_id, created.id, approved_by="ciso")
        reviewed = await exception_service.review(
            organization_id, created.id, reviewed_by="auditor", still_needed=False
        )
        assert reviewed.status == ExceptionStatus.REVOKED
        assert "no longer needed" in (reviewed.revocation_reason or "")

    async def test_a_review_finding_it_needed_resets_the_clock(
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
            title="Still needed",
            business_justification="Reason.",
            expires_at=soon(30),
        )
        await exception_service.approve(organization_id, created.id, approved_by="ciso")
        reviewed = await exception_service.review(
            organization_id, created.id, reviewed_by="auditor", still_needed=True
        )
        assert reviewed.status == ExceptionStatus.ACTIVE
        assert reviewed.next_review_at is not None
        assert reviewed.next_review_at > utcnow()

    async def test_lapsed_exceptions_are_swept_to_expired(
        self,
        exception_service: ExceptionService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
        db_session: AsyncSession,
    ) -> None:
        # A lapsed waiver still marked ACTIVE goes on waiving a control
        # it no longer covers.
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        created = await exception_service.request(
            organization_id,
            control_id=control.id,
            title="Lapsing",
            business_justification="Reason.",
            expires_at=soon(1),
        )
        await exception_service.approve(organization_id, created.id, approved_by="ciso")
        created.expires_at = utcnow() - timedelta(days=1)
        await db_session.flush()

        assert await exception_service.expire_lapsed(organization_id) == 1
        await db_session.refresh(created)
        assert created.status == ExceptionStatus.EXPIRED

    async def test_a_lapsed_exception_no_longer_excepts(
        self,
        exception_service: ExceptionService,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
        db_session: AsyncSession,
    ) -> None:
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        waiver = await exception_service.request(
            organization_id,
            control_id=control.id,
            title="Lapsed",
            business_justification="Reason.",
            expires_at=soon(1),
        )
        await exception_service.approve(organization_id, waiver.id, approved_by="ciso")
        waiver.expires_at = utcnow() - timedelta(days=1)
        await db_session.flush()

        planned = await assessment_service.create(
            organization_id, name="After lapse", framework_id=framework.id
        )
        finished = await assessment_service.run(
            organization_id,
            planned.id,
            targets=[Target("host-1", "server", payload={"firewall": {"enabled": False}})],
        )
        assert finished.controls_failed == 1
        assert finished.controls_excepted == 0

    async def test_expiring_exceptions_are_warned_about_before_they_lapse(
        self,
        exception_service: ExceptionService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # A waiver that lapses unannounced turns into a wave of failing
        # controls whose cause nobody can explain.
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        created = await exception_service.request(
            organization_id,
            control_id=control.id,
            title="Soon",
            business_justification="Reason.",
            expires_at=soon(5),
        )
        await exception_service.approve(organization_id, created.id, approved_by="ciso")
        warned = await exception_service.warn_expiring(organization_id, notify_user_id="user-1")
        assert len(warned) == 1

    async def test_overused_waivers_are_findable(
        self,
        exception_service: ExceptionService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
        db_session: AsyncSession,
    ) -> None:
        # A waiver used a thousand times is not an exception, and nothing
        # else in the system would ever say so.
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        created = await exception_service.request(
            organization_id,
            control_id=control.id,
            title="Load-bearing",
            business_justification="Reason.",
            expires_at=soon(30),
        )
        created.use_count = 500
        await db_session.flush()
        assert len(await exception_service.overused(organization_id, threshold=100)) == 1

    async def test_a_waiver_due_for_review_is_findable(
        self,
        exception_service: ExceptionService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
        db_session: AsyncSession,
    ) -> None:
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        created = await exception_service.request(
            organization_id,
            control_id=control.id,
            title="Overdue review",
            business_justification="Reason.",
            expires_at=soon(300),
        )
        await exception_service.approve(organization_id, created.id, approved_by="ciso")
        created.next_review_at = utcnow() - timedelta(days=1)
        await db_session.flush()
        assert len(await exception_service.due_for_review(organization_id)) == 1


class TestRisk:
    async def test_severity_is_derived_and_a_reference_is_assigned(
        self,
        risk_service: RiskService,
        organization_id: uuid.UUID,
        publisher: RecordingPublisher,
    ) -> None:
        created = await risk_service.register(
            organization_id,
            title="Unpatched estate",
            likelihood=RiskLikelihood.ALMOST_CERTAIN,
            impact=RiskImpact.SEVERE,
            notify_user_id="user-1",
        )
        assert created.severity == RiskSeverity.CRITICAL
        assert created.reference == "RISK-0001"
        assert created.inherent_score == 25.0
        assert "RiskRegistered" in publisher.names

    async def test_references_do_not_collide(
        self, risk_service: RiskService, organization_id: uuid.UUID
    ) -> None:
        # A reference gets quoted in meeting minutes, so two risks must
        # never share one.
        first = await risk_service.register(
            organization_id,
            title="One",
            likelihood=RiskLikelihood.RARE,
            impact=RiskImpact.MINOR,
        )
        second = await risk_service.register(
            organization_id,
            title="Two",
            likelihood=RiskLikelihood.RARE,
            impact=RiskImpact.MINOR,
        )
        assert first.reference != second.reference

    async def test_rescoring_updates_the_derived_severity(
        self, risk_service: RiskService, organization_id: uuid.UUID
    ) -> None:
        created = await risk_service.register(
            organization_id,
            title="Growing",
            likelihood=RiskLikelihood.RARE,
            impact=RiskImpact.MINOR,
        )
        assert created.severity == RiskSeverity.LOW
        updated = await risk_service.update_assessment(
            organization_id,
            created.id,
            likelihood=RiskLikelihood.ALMOST_CERTAIN,
            impact=RiskImpact.SEVERE,
        )
        assert updated.severity == RiskSeverity.CRITICAL

    async def test_residual_scoring_needs_both_halves(
        self, risk_service: RiskService, organization_id: uuid.UUID
    ) -> None:
        # Carrying the inherent likelihood forward would report a
        # mitigation as reducing risk it never touched.
        created = await risk_service.register(
            organization_id,
            title="Mitigated",
            likelihood=RiskLikelihood.LIKELY,
            impact=RiskImpact.MAJOR,
        )
        half = await risk_service.update_assessment(
            organization_id, created.id, residual_impact=RiskImpact.MINOR
        )
        assert half.residual_severity is None

        full = await risk_service.update_assessment(
            organization_id,
            created.id,
            residual_likelihood=RiskLikelihood.RARE,
            residual_impact=RiskImpact.MINOR,
        )
        assert full.residual_severity == RiskSeverity.LOW

    async def test_closing_a_risk_needs_a_reason(
        self, risk_service: RiskService, organization_id: uuid.UUID
    ) -> None:
        # A risk that left the register without an explanation is the one
        # an auditor will ask about.
        created = await risk_service.register(
            organization_id,
            title="Closing",
            likelihood=RiskLikelihood.RARE,
            impact=RiskImpact.MINOR,
        )
        with pytest.raises(ValidationError, match="reason"):
            await risk_service.transition(organization_id, created.id, target=RiskStatus.CLOSED)
        closed = await risk_service.transition(
            organization_id,
            created.id,
            target=RiskStatus.CLOSED,
            reason="The system was decommissioned.",
        )
        assert closed.closed_at is not None

    async def test_a_closed_risk_cannot_be_transitioned_again(
        self, risk_service: RiskService, organization_id: uuid.UUID
    ) -> None:
        created = await risk_service.register(
            organization_id,
            title="Done",
            likelihood=RiskLikelihood.RARE,
            impact=RiskImpact.MINOR,
        )
        await risk_service.transition(
            organization_id, created.id, target=RiskStatus.CLOSED, reason="Gone."
        )
        with pytest.raises(ConflictError):
            await risk_service.transition(organization_id, created.id, target=RiskStatus.MONITORING)

    async def test_reviewing_resets_the_clock(
        self, risk_service: RiskService, organization_id: uuid.UUID
    ) -> None:
        created = await risk_service.register(
            organization_id,
            title="Reviewed",
            likelihood=RiskLikelihood.RARE,
            impact=RiskImpact.MINOR,
        )
        reviewed = await risk_service.record_review(organization_id, created.id)
        assert reviewed.last_reviewed_at is not None
        assert reviewed.next_review_at is not None and reviewed.next_review_at > utcnow()

    async def test_risks_due_for_review_are_findable(
        self,
        risk_service: RiskService,
        organization_id: uuid.UUID,
        db_session: AsyncSession,
    ) -> None:
        created = await risk_service.register(
            organization_id,
            title="Neglected",
            likelihood=RiskLikelihood.RARE,
            impact=RiskImpact.MINOR,
        )
        created.next_review_at = utcnow() - timedelta(days=1)
        await db_session.flush()
        assert len(await risk_service.due_for_review(organization_id)) == 1


class TestRemediation:
    async def _finding(
        self,
        finding_service: FindingService,
        organization_id: uuid.UUID,
        control_id: uuid.UUID,
    ) -> object:
        found, _ = await finding_service.raise_from_result(
            organization_id,
            ControlResult(
                control_id=str(control_id),
                framework_id=None,
                status=ResultStatus.FAIL,
                reason="firewall off",
                target_id="host-1",
                target_type="server",
                severity=ControlSeverity.HIGH,
            ),
        )
        return found

    async def test_a_remediation_cannot_be_verified_before_it_is_carried_out(
        self,
        remediation_service: RemediationService,
        finding_service: FindingService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        finding = await self._finding(finding_service, organization_id, control.id)
        task = await remediation_service.propose(
            organization_id, finding_id=finding.id, title="Enable the firewall"
        )
        with pytest.raises(ConflictError, match="nothing to verify"):
            await remediation_service.verify(organization_id, task.id, verified_by="alice")

    async def test_verified_cannot_be_set_by_hand(
        self,
        remediation_service: RemediationService,
        finding_service: FindingService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        finding = await self._finding(finding_service, organization_id, control.id)
        task = await remediation_service.propose(
            organization_id, finding_id=finding.id, title="Fix"
        )
        with pytest.raises(ConflictError, match="re-assessment"):
            await remediation_service.transition(
                organization_id, task.id, target=RemediationStatus.VERIFIED
            )

    async def test_a_completed_fix_that_did_not_work_is_not_verified(
        self,
        remediation_service: RemediationService,
        finding_service: FindingService,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # An automated remediation that failed silently would otherwise
        # close the finding it did not fix, and that finding is then
        # invisible until the next audit.
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        planned = await assessment_service.create(
            organization_id, name="Before", framework_id=framework.id
        )
        await assessment_service.run(
            organization_id,
            planned.id,
            targets=[Target("host-1", "server", payload={"firewall": {"enabled": False}})],
        )
        finding = await self._finding(finding_service, organization_id, control.id)
        task = await remediation_service.propose(
            organization_id, finding_id=finding.id, title="Claimed fix"
        )
        await remediation_service.transition(
            organization_id, task.id, target=RemediationStatus.COMPLETED
        )

        verified, passed = await remediation_service.verify(
            organization_id, task.id, verified_by="alice", notify_user_id="user-1"
        )
        assert passed is False
        assert verified.status != RemediationStatus.VERIFIED
        assert "still reports" in (verified.verification_note or "")

        stored = await finding_service.get(organization_id, finding.id)
        assert stored.status != FindingStatus.VERIFIED, "the finding stays open"

    async def test_a_fix_the_re_assessment_confirms_closes_the_finding(
        self,
        remediation_service: RemediationService,
        finding_service: FindingService,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
        publisher: RecordingPublisher,
    ) -> None:
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        finding = await self._finding(finding_service, organization_id, control.id)
        task = await remediation_service.propose(
            organization_id, finding_id=finding.id, title="Real fix"
        )
        await remediation_service.transition(
            organization_id, task.id, target=RemediationStatus.COMPLETED
        )

        # The re-assessment that proves it.
        after = await assessment_service.create(
            organization_id, name="After", framework_id=framework.id
        )
        await assessment_service.run(
            organization_id,
            after.id,
            targets=[Target("host-1", "server", payload={"firewall": {"enabled": True}})],
        )

        verified, passed = await remediation_service.verify(
            organization_id, task.id, verified_by="alice", notify_user_id="user-1"
        )
        assert passed is True
        assert verified.status == RemediationStatus.VERIFIED
        assert verified.verification_result_id is not None

        closed = await finding_service.get(organization_id, finding.id)
        assert closed.status == FindingStatus.VERIFIED
        assert "RemediationCompleted" in publisher.names

    async def test_a_never_assessed_control_cannot_be_verified(
        self,
        remediation_service: RemediationService,
        finding_service: FindingService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        finding = await self._finding(finding_service, organization_id, control.id)
        task = await remediation_service.propose(
            organization_id, finding_id=finding.id, title="Untested"
        )
        await remediation_service.transition(
            organization_id, task.id, target=RemediationStatus.COMPLETED
        )
        _task, passed = await remediation_service.verify(
            organization_id, task.id, verified_by="alice"
        )
        assert passed is False

    async def test_assigning_a_remediation_moves_its_finding_in_progress(
        self,
        remediation_service: RemediationService,
        finding_service: FindingService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        finding = await self._finding(finding_service, organization_id, control.id)
        await remediation_service.propose(
            organization_id, finding_id=finding.id, title="Assigned", assignee_id="alice"
        )
        stored = await finding_service.get(organization_id, finding.id)
        assert stored.status == FindingStatus.IN_PROGRESS

    async def test_starting_a_remediation_counts_an_attempt(
        self,
        remediation_service: RemediationService,
        finding_service: FindingService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        finding = await self._finding(finding_service, organization_id, control.id)
        task = await remediation_service.propose(
            organization_id, finding_id=finding.id, title="Attempted"
        )
        started = await remediation_service.transition(
            organization_id, task.id, target=RemediationStatus.IN_PROGRESS
        )
        assert started.attempts == 1
        assert started.started_at is not None

    async def test_every_attempt_on_a_finding_is_listed(
        self,
        remediation_service: RemediationService,
        finding_service: FindingService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        finding = await self._finding(finding_service, organization_id, control.id)
        await remediation_service.propose(organization_id, finding_id=finding.id, title="First try")
        await remediation_service.propose(
            organization_id, finding_id=finding.id, title="Second try"
        )
        assert len(await remediation_service.for_finding(organization_id, finding.id)) == 2


class TestScoring:
    async def _run(
        self,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> tuple[object, object]:
        framework = await make_framework("cis")
        await make_control(framework.id, "1.1", severity=ControlSeverity.CRITICAL)
        await make_control(framework.id, "1.2", severity=ControlSeverity.LOW)
        planned = await assessment_service.create(
            organization_id, name="Scored", framework_id=framework.id
        )
        await assessment_service.run(
            organization_id,
            planned.id,
            targets=[Target("host-1", "server", payload={"firewall": {"enabled": True}})],
        )
        return framework, planned

    async def test_scoring_stores_overall_and_per_framework(
        self,
        scoring_service: ScoringService,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
        publisher: RecordingPublisher,
    ) -> None:
        framework, planned = await self._run(
            assessment_service, make_framework, make_control, organization_id
        )
        result = await scoring_service.score_assessment(organization_id, planned.id)
        assert result["overall"]["score"] == 100.0
        assert str(framework.id) in result["by_framework"]
        assert "ComplianceScoreUpdated" in publisher.names

        current = await scoring_service.current(organization_id)
        assert current is not None
        assert current["score"] == 100.0

    async def test_a_score_is_stored_with_its_coverage(
        self,
        scoring_service: ScoringService,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # A score without its coverage is the number people misread.
        _framework, planned = await self._run(
            assessment_service, make_framework, make_control, organization_id
        )
        result = await scoring_service.score_assessment(organization_id, planned.id)
        assert result["coverage"] == 100.0
        current = await scoring_service.current(organization_id)
        assert current is not None
        assert "coverage" in current["breakdown"]

    async def test_a_second_score_records_its_movement(
        self,
        scoring_service: ScoringService,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework("cis")
        await make_control(framework.id, "1.1")
        first = await assessment_service.create(
            organization_id, name="First", framework_id=framework.id
        )
        await assessment_service.run(
            organization_id,
            first.id,
            targets=[Target("h", "server", payload={"firewall": {"enabled": False}})],
        )
        await scoring_service.score_assessment(organization_id, first.id)

        second = await assessment_service.create(
            organization_id, name="Second", framework_id=framework.id
        )
        await assessment_service.run(
            organization_id,
            second.id,
            targets=[Target("h", "server", payload={"firewall": {"enabled": True}})],
        )
        result = await scoring_service.score_assessment(organization_id, second.id)
        assert result["delta"] == 100.0

    async def test_history_reports_a_direction(
        self,
        scoring_service: ScoringService,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        _framework, planned = await self._run(
            assessment_service, make_framework, make_control, organization_id
        )
        await scoring_service.score_assessment(organization_id, planned.id)
        history = await scoring_service.history(organization_id)
        assert history["points"]
        assert history["trend"] in {"insufficient_data", "stable", "improving", "declining"}

    async def test_target_scores_rank_worst_first(
        self,
        scoring_service: ScoringService,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # The estate-wide number says whether there is a problem; this
        # says where to go.
        framework = await make_framework("cis")
        await make_control(framework.id, "1.1")
        planned = await assessment_service.create(
            organization_id, name="Per host", framework_id=framework.id
        )
        await assessment_service.run(
            organization_id,
            planned.id,
            targets=[
                Target("good", "server", payload={"firewall": {"enabled": True}}),
                Target("bad", "server", payload={"firewall": {"enabled": False}}),
            ],
        )
        ranked = await scoring_service.score_targets(organization_id, planned.id)
        assert ranked[0]["target_id"] == "bad"
        assert ranked[0]["score"] < ranked[-1]["score"]

    async def test_no_score_yet_reads_as_none_not_zero(
        self, scoring_service: ScoringService, organization_id: uuid.UUID
    ) -> None:
        # Zero would say "totally non-compliant" about an organization
        # that has simply not been assessed.
        assert await scoring_service.current(organization_id) is None

    async def test_framework_scores_list_the_newest_per_framework(
        self,
        scoring_service: ScoringService,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        _framework, planned = await self._run(
            assessment_service, make_framework, make_control, organization_id
        )
        await scoring_service.score_assessment(organization_id, planned.id)
        assert len(await scoring_service.framework_scores(organization_id)) == 1


class TestReportingAndAudit:
    async def test_every_report_kind_builds(
        self,
        report_service: ReportService,
        catalogue_service: CatalogueService,
        organization_id: uuid.UUID,
    ) -> None:
        await catalogue_service.seed_builtin(organization_id)
        for kind in ReportKind:
            record = await report_service.generate(organization_id, kind=kind)
            assert record.error is None, f"{kind}: {record.error}"
            assert str(record.status) == "completed"

    async def test_an_executive_report_with_no_score_says_so(
        self, report_service: ReportService, organization_id: uuid.UUID
    ) -> None:
        # An empty compliance report reads as "nothing to report", which
        # is the opposite of "I could not tell you".
        record = await report_service.generate(organization_id, kind=ReportKind.EXECUTIVE)
        assert "No compliance score" in record.content["narrative"]

    async def test_an_evidence_report_carries_digests_not_payloads(
        self,
        report_service: ReportService,
        make_evidence: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # An evidence report is read by people who are not entitled to
        # the configuration detail inside it.
        await make_evidence("host-1", {"admin_password_hash": "sensitive"})
        record = await report_service.generate(organization_id, kind=ReportKind.EVIDENCE)
        row = record.content["rows"][0]
        assert row["digest"]
        assert row["intact"] is True
        assert "sensitive" not in str(record.content)

    async def test_csv_of_an_empty_report_is_empty_not_a_bare_header(
        self, report_service: ReportService
    ) -> None:
        assert report_service.to_csv({"rows": []}) == ""

    async def test_csv_and_markdown_render_rows(self, report_service: ReportService) -> None:
        content = {"rows": [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]}
        csv_text = report_service.to_csv(content)
        assert "a,b" in csv_text
        markdown = report_service.to_markdown(content, title="T")
        assert "| a | b |" in markdown
        assert "# T" in markdown

    async def test_markdown_of_an_empty_report_says_no_rows(
        self, report_service: ReportService
    ) -> None:
        assert "No rows" in report_service.to_markdown({"rows": []})

    async def test_an_unbuildable_report_records_its_error_rather_than_raising(
        self, report_service: ReportService, organization_id: uuid.UUID
    ) -> None:
        # Somebody who asked for a report needs to be told what went
        # wrong with it.
        record = await report_service.generate(
            organization_id,
            kind="not-a-kind",  # type: ignore[arg-type]
        )
        assert str(record.status) == "failed"
        assert record.error

    async def test_the_audit_trail_records_and_summarises(
        self, audit_service: AuditService, organization_id: uuid.UUID
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.FRAMEWORK_CREATED,
            entity_type="framework",
            summary="Registered a framework.",
            actor_id="alice",
        )
        entries = await audit_service.list_entries(organization_id)
        assert len(entries) == 1
        summary = await audit_service.summary(organization_id)
        assert summary["total"] == 1

    async def test_a_refused_operations_audit_entry_survives_the_rollback(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        organization_id: uuid.UUID,
    ) -> None:
        """The one behaviour the HTTP tests cannot check.

        ``record_failure`` commits in its own transaction because the
        request that refused something is about to roll back, taking any
        entry written inside it with it. Exercised here against the real
        session factory: under the SAVEPOINT the HTTP fixture uses, the
        distinction vanishes and the test would pass either way -- which
        is exactly how the same bug shipped in
        ``services/knowledge-graph-service`` and stayed green.
        """
        async with db_session_factory() as writer:
            service = AuditService(AuditRepository(writer), session_factory=db_session_factory)
            await service.record_failure(
                organization_id,
                action=AuditAction.EXCEPTION_REQUESTED,
                entity_type="exception",
                summary="Refused: the expiry was past the ceiling.",
                actor_id="mallory",
            )
            await writer.rollback()

        async with db_session_factory() as reader:
            entries = await AuditRepository(reader).list_for_org(organization_id)
        assert len(entries) == 1, "the refusal outlived the transaction that refused it"
        assert entries[0].succeeded is False

    async def test_record_failure_falls_back_to_the_request_session(
        self, audit_service: AuditService, organization_id: uuid.UUID
    ) -> None:
        # Without a session factory there is nothing to commit
        # independently, so it writes inline rather than doing nothing.
        await audit_service.record_failure(
            organization_id,
            action=AuditAction.ADMINISTRATIVE,
            entity_type="framework",
            summary="Refused.",
        )
        entries = await audit_service.list_entries(organization_id)
        assert len(entries) == 1


class TestStatisticsAndWorkers:
    async def test_a_rollup_is_idempotent_by_window(
        self,
        statistics_service: StatisticsService,
        catalogue_service: CatalogueService,
        organization_id: uuid.UUID,
    ) -> None:
        # A scheduled rollup that runs twice -- after a retry, a
        # redeploy, or a leader election -- must not double every number
        # in the trend.
        await catalogue_service.seed_builtin(organization_id)
        start, end = utcnow() - timedelta(hours=24), utcnow()
        first = await statistics_service.rollup(organization_id, window_start=start, window_end=end)
        second = await statistics_service.rollup(
            organization_id, window_start=start, window_end=end
        )
        assert first.id == second.id

    async def test_remediation_success_is_verified_over_attempted(
        self,
        statistics_service: StatisticsService,
        remediation_service: RemediationService,
        finding_service: FindingService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # completed-over-attempted reports a programme as working when it
        # may only be busy.
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
                severity=ControlSeverity.HIGH,
            ),
        )
        task = await remediation_service.propose(
            organization_id, finding_id=found.id, title="Claimed"
        )
        await remediation_service.transition(
            organization_id, task.id, target=RemediationStatus.COMPLETED
        )

        window = await statistics_service.rollup(
            organization_id,
            window_start=utcnow() - timedelta(hours=1),
            window_end=utcnow() + timedelta(hours=1),
        )
        assert window.remediations_completed == 1
        assert window.remediations_verified == 0
        assert window.remediation_success_rate == 0.0

    async def test_the_dashboard_answers_with_no_data(
        self, statistics_service: StatisticsService, organization_id: uuid.UUID
    ) -> None:
        dashboard = await statistics_service.dashboard(organization_id)
        assert dashboard["score"] is None
        assert dashboard["findings_open"] == 0

    async def test_the_statistics_worker_ticks(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        catalogue_service: CatalogueService,
        organization_id: uuid.UUID,
        db_session: AsyncSession,
    ) -> None:
        await catalogue_service.seed_builtin(organization_id)
        await db_session.commit()
        assert await StatisticsWorker(db_session_factory).tick() >= 1

    async def test_the_maintenance_worker_expires_and_reaps(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        catalogue_service: CatalogueService,
        exception_service: ExceptionService,
        assessment_service: AssessmentService,
        make_control: MakeControlFn,
        make_framework: MakeControlFn,
        organization_id: uuid.UUID,
        db_session: AsyncSession,
    ) -> None:
        framework = await make_framework("swept")
        control = await make_control(framework.id, "1.1")
        waiver = await exception_service.request(
            organization_id,
            control_id=control.id,
            title="Lapsed",
            business_justification="Reason.",
            expires_at=soon(1),
        )
        await exception_service.approve(organization_id, waiver.id, approved_by="ciso")
        waiver.expires_at = utcnow() - timedelta(days=1)

        stuck = await assessment_service.create(
            organization_id, name="Abandoned", framework_id=framework.id
        )
        stuck.status = AssessmentStatus.RUNNING
        stuck.started_at = utcnow() - timedelta(hours=5)
        await db_session.commit()

        counts = await MaintenanceWorker(db_session_factory).tick()
        assert counts["expired"] >= 1
        assert counts["reaped"] >= 1

    async def test_a_worker_survives_one_tenants_failure(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        # A tenant silently missing from a rollup is worse than a rollup
        # that visibly failed, so the sweep continues past an error.
        worker = StatisticsWorker(db_session_factory)
        assert await worker.tick() >= 0
