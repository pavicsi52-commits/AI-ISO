"""Running assessments.

The orchestrator: loads controls, waivers, and evidence, hands them to
the pure engine, and persists what comes back.

**Everything that could be pure is pure.** This module reads and writes;
``app/assessments/engine.py`` decides. That split is what makes a verdict
reproducible -- an auditor asking why a control failed last March gets an
answer derived from the evidence that was stored, not from whatever the
estate looks like today.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.assessments.engine import (
    AssessmentOutcome,
    ControlResult,
    EvaluableControl,
    Target,
    control_from_row,
    evaluate_assessment,
    waiver_from_row,
)
from app.events.compliance_events import (
    SOURCE_SERVICE,
    ComplianceAssessmentCompletedEvent,
    ComplianceAssessmentStartedEvent,
)
from app.models.assessment import ComplianceAssessment, ComplianceResult
from app.models.enums import (
    AssessmentKind,
    AssessmentScope,
    AssessmentStatus,
    ControlSeverity,
    ResultStatus,
    assessment_status_of,
)
from app.repositories.catalogue import ControlRepository, FrameworkRepository
from app.repositories.governance import ExceptionRepository
from app.repositories.runs import AssessmentRepository, EvidenceRepository, ResultRepository
from app.scoring.engine import ScoredResult, compute_score, coverage_of
from app.services.evidence import EvidenceService
from app.types import EventPublisher

logger = get_logger("app.services.assessment")


class AssessmentService:
    """Plans, runs, and records compliance assessments."""

    def __init__(
        self,
        assessments: AssessmentRepository,
        results: ResultRepository,
        controls: ControlRepository,
        frameworks: FrameworkRepository,
        exceptions: ExceptionRepository,
        evidence: EvidenceRepository,
        *,
        publish_event: EventPublisher | None = None,
        max_controls: int = 2_000,
        max_targets_per_control: int = 5_000,
        max_seconds: float = 300.0,
    ) -> None:
        self._assessments = assessments
        self._results = results
        self._controls = controls
        self._frameworks = frameworks
        self._exceptions = exceptions
        self._evidence = evidence
        self._publish = publish_event
        self._max_controls = max_controls
        self._max_targets = max_targets_per_control
        self._max_seconds = max_seconds

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def create(
        self,
        organization_id: UUID,
        *,
        name: str,
        kind: AssessmentKind = AssessmentKind.ON_DEMAND,
        scope: AssessmentScope = AssessmentScope.ORGANIZATION,
        scope_id: str | None = None,
        framework_id: UUID | None = None,
        description: str | None = None,
        parameters: dict[str, Any] | None = None,
        triggered_by: str | None = None,
        actor_id: UUID | None = None,
    ) -> ComplianceAssessment:
        """Plan an assessment.

        Raises:
            NotFoundError: If the named framework does not exist here.
        """
        if framework_id is not None:
            await self._frameworks.require_in_org(organization_id, framework_id)
        return await self._assessments.create(
            ComplianceAssessment(
                organization_id=organization_id,
                name=name,
                description=description,
                kind=kind,
                scope=scope,
                scope_id=scope_id,
                framework_id=framework_id,
                status=AssessmentStatus.PENDING,
                parameters=dict(parameters or {}),
                triggered_by=triggered_by,
                created_by=actor_id,
            )
        )

    async def run(
        self,
        organization_id: UUID,
        assessment_id: UUID,
        *,
        targets: list[Target] | None = None,
        now: datetime | None = None,
        actor_id: UUID | None = None,
    ) -> ComplianceAssessment:
        """Execute a planned assessment and record everything it found.

        A run that exceeds its wall-clock budget finishes as ``PARTIAL``
        rather than being discarded: half an assessment honestly labelled
        is worth more than none, and far more than a whole one that never
        terminates.

        Raises:
            ConflictError: If the run has already finished. Re-running
                would overwrite the results an audit may already have
                been shown, and the correct action is a new assessment.
        """
        stored = await self._assessments.require_in_org(organization_id, assessment_id)
        current = assessment_status_of(stored)
        if current is not AssessmentStatus.PENDING:
            raise ConflictError(
                f"Assessment {stored.name!r} is {str(current)!r} and cannot be run again. "
                "Create a new assessment rather than overwriting results an audit may "
                "already have been shown."
            )

        moment = now or datetime.now(UTC)
        started = time.perf_counter()
        stored.status = AssessmentStatus.RUNNING
        stored.started_at = moment
        stored.updated_by = actor_id
        await self._assessments.update(stored)

        await self._publish_event(
            ComplianceAssessmentStartedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "assessment_id": str(assessment_id),
                    "name": stored.name,
                    "scope": str(stored.scope),
                    "framework_id": str(stored.framework_id) if stored.framework_id else None,
                },
            )
        )

        try:
            outcome = await self._evaluate(organization_id, stored, targets or [], moment=moment)
        except Exception as exc:
            # A failed run is recorded as FAILED with its reason rather
            # than left RUNNING forever. A stuck row blocks the next
            # scheduled run for that framework, so an unhandled error
            # here would quietly stop an organization being assessed at
            # all -- the worst possible failure for this service.
            stored.status = AssessmentStatus.FAILED
            stored.completed_at = datetime.now(UTC)
            stored.duration_ms = (time.perf_counter() - started) * 1_000
            stored.error = str(exc)
            await self._assessments.update(stored)
            logger.exception(
                "A compliance assessment failed and was recorded as FAILED.",
                extra={
                    "extra_fields": {
                        "organization_id": str(organization_id),
                        "assessment_id": str(assessment_id),
                    }
                },
            )
            raise

        await self._persist(organization_id, stored, outcome, moment=moment, actor_id=actor_id)

        elapsed = time.perf_counter() - started
        stored.duration_ms = elapsed * 1_000
        stored.completed_at = datetime.now(UTC)
        stored.status = (
            AssessmentStatus.PARTIAL
            if outcome.truncated or elapsed > self._max_seconds
            else AssessmentStatus.COMPLETED
        )
        if outcome.truncated:
            stored.error = outcome.truncation_reason
        elif elapsed > self._max_seconds:
            stored.error = (
                f"The run took {elapsed:.1f}s, past the {self._max_seconds:.0f}s budget; "
                "results are recorded but coverage may be incomplete."
            )
        stored.updated_by = actor_id
        finished = await self._assessments.update(stored)

        await self._publish_event(
            ComplianceAssessmentCompletedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "assessment_id": str(assessment_id),
                    "name": finished.name,
                    "status": str(finished.status),
                    "score": finished.score,
                    "controls_total": finished.controls_total,
                    "controls_failed": finished.controls_failed,
                    "findings_raised": finished.findings_raised,
                    "truncated": outcome.truncated,
                },
            )
        )
        return finished

    async def _evaluate(
        self,
        organization_id: UUID,
        assessment: ComplianceAssessment,
        targets: list[Target],
        *,
        moment: datetime,
    ) -> AssessmentOutcome:
        """Load everything the engine needs and let it decide."""
        framework_ids = [assessment.framework_id] if assessment.framework_id else None
        rows = await self._controls.list_assessable(
            organization_id,
            framework_ids=framework_ids,
            automatable_only=False,
            limit=self._max_controls + 1,
        )
        controls = self._loadable(rows)

        waivers = [
            waiver_from_row(one)
            for one in await self._exceptions.list_live(organization_id, moment=moment)
        ]

        enriched = await self._with_evidence(organization_id, targets)

        return evaluate_assessment(
            controls,
            enriched,
            now=moment,
            waivers=waivers,
            max_controls=self._max_controls,
            max_targets_per_control=self._max_targets,
        )

    def _loadable(self, rows: list[Any]) -> list[EvaluableControl]:
        """Project control rows, skipping any that will not load.

        A control whose stored rule names an operator that no longer
        exists is logged and left out rather than aborting the run. One
        corrupt row must not stop an organization being assessed -- but
        the skip is loud, because a control that silently stopped
        applying is exactly the failure this service exists to prevent.
        """
        loaded: list[EvaluableControl] = []
        for row in rows:
            try:
                loaded.append(control_from_row(row))
            except Exception as exc:
                logger.warning(
                    "A control could not be loaded for assessment and was skipped.",
                    extra={
                        "extra_fields": {
                            "control_id": str(row.id),
                            "code": row.code,
                            "error": str(exc),
                        }
                    },
                )
        return loaded

    async def _with_evidence(self, organization_id: UUID, targets: list[Target]) -> list[Target]:
        """Attach stored evidence to any target that arrived without it.

        A caller who supplies a payload is believed -- that is how a
        collector pushes fresh data through a scan. A caller who names a
        target without one gets whatever this service already holds, so
        an assessment can be re-run from stored evidence alone. Which is
        the property that makes a historical assessment reproducible.
        """
        needing = [one.target_id for one in targets if not one.payload and one.target_id]
        if not needing:
            return targets

        service = EvidenceService(self._evidence)
        merged = await service.payload_for_targets(organization_id, needing)
        return [
            (
                one
                if one.payload or not one.target_id
                else Target(
                    target_id=one.target_id,
                    target_type=one.target_type,
                    name=one.name,
                    payload=merged.get(one.target_id, {}),
                    evidence_id=one.evidence_id,
                )
            )
            for one in targets
        ]

    async def _persist(
        self,
        organization_id: UUID,
        assessment: ComplianceAssessment,
        outcome: AssessmentOutcome,
        *,
        moment: datetime,
        actor_id: UUID | None,
    ) -> None:
        """Write every result and roll the totals onto the assessment."""
        for result in outcome.results:
            await self._results.create(
                ComplianceResult(
                    organization_id=organization_id,
                    assessment_id=assessment.id,
                    control_id=UUID(result.control_id),
                    framework_id=UUID(result.framework_id) if result.framework_id else None,
                    target_type=result.target_type,
                    target_id=result.target_id or None,
                    target_name=result.target_name,
                    status=result.status,
                    reason=result.reason,
                    expected=result.expected,
                    observed=result.observed,
                    evaluated_at=moment,
                    evidence_id=UUID(result.evidence_id) if result.evidence_id else None,
                    exception_id=UUID(result.exception_id) if result.exception_id else None,
                    error=result.error,
                    created_by=actor_id,
                )
            )
            if result.exception_id:
                await self._exceptions.record_use(UUID(result.exception_id), moment=moment)

        counts = outcome.counts()
        assessment.controls_total = len(outcome.results)
        assessment.controls_passed = counts[str(ResultStatus.PASS)]
        assessment.controls_failed = counts[str(ResultStatus.FAIL)]
        assessment.controls_warning = counts[str(ResultStatus.WARNING)]
        assessment.controls_not_applicable = counts[str(ResultStatus.NOT_APPLICABLE)]
        assessment.controls_not_assessed = counts[str(ResultStatus.NOT_ASSESSED)]
        assessment.controls_errored = counts[str(ResultStatus.ERROR)]
        assessment.controls_excepted = counts[str(ResultStatus.EXCEPTED)]

        scored = [
            ScoredResult(
                control_id=one.control_id,
                status=one.status,
                severity=one.severity,
                framework_id=one.framework_id,
                target_id=one.target_id,
            )
            for one in outcome.results
        ]
        breakdown = compute_score(scored)
        assessment.score = round(breakdown.score, 2)
        assessment.summary = {
            **breakdown.as_dict(),
            "coverage": round(coverage_of(scored), 2),
            "truncated": outcome.truncated,
            "truncation_reason": outcome.truncation_reason,
        }

    async def get(self, organization_id: UUID, assessment_id: UUID) -> ComplianceAssessment:
        """One assessment.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._assessments.require_in_org(organization_id, assessment_id)

    async def list_assessments(
        self,
        organization_id: UUID,
        *,
        status: AssessmentStatus | None = None,
        framework_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ComplianceAssessment]:
        """Assessments, newest first."""
        return await self._assessments.list_for_org(
            organization_id,
            status=status,
            framework_id=framework_id,
            limit=limit,
            offset=offset,
        )

    async def results_for(
        self,
        organization_id: UUID,
        assessment_id: UUID,
        *,
        status: ResultStatus | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[ComplianceResult]:
        """One run's results, paged.

        Raises:
            NotFoundError: If the assessment does not exist here.
        """
        await self._assessments.require_in_org(organization_id, assessment_id)
        return await self._results.list_for_assessment(
            organization_id, assessment_id, status=status, limit=limit, offset=offset
        )

    async def cancel(
        self, organization_id: UUID, assessment_id: UUID, *, actor_id: UUID | None = None
    ) -> ComplianceAssessment:
        """Stop a planned or running assessment.

        Raises:
            ConflictError: If it has already finished.
        """
        stored = await self._assessments.require_in_org(organization_id, assessment_id)
        current = assessment_status_of(stored)
        if current in (
            AssessmentStatus.COMPLETED,
            AssessmentStatus.FAILED,
            AssessmentStatus.CANCELLED,
            AssessmentStatus.PARTIAL,
        ):
            raise ConflictError(
                f"Assessment {stored.name!r} has already finished as {str(current)!r}."
            )
        stored.status = AssessmentStatus.CANCELLED
        stored.completed_at = datetime.now(UTC)
        stored.updated_by = actor_id
        return await self._assessments.update(stored)

    async def reap_stuck(
        self, organization_id: UUID, *, older_than_minutes: int = 60
    ) -> list[ComplianceAssessment]:
        """Fail assessments whose worker died mid-run.

        A ``RUNNING`` row left by a crashed worker never clears itself,
        and while it stands it blocks the next scheduled run for that
        framework. Without this sweep, one crash silently stops an
        organization being assessed until somebody notices -- which,
        given that the symptom is *nothing happening*, could be a very
        long time.
        """
        cutoff = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
        stuck = await self._assessments.list_stuck(organization_id, older_than=cutoff)
        reaped: list[ComplianceAssessment] = []
        for one in stuck:
            one.status = AssessmentStatus.FAILED
            one.completed_at = datetime.now(UTC)
            one.error = (
                f"No progress for over {older_than_minutes} minutes; the worker running "
                "this assessment is presumed to have died."
            )
            reaped.append(await self._assessments.update(one))
        if reaped:
            logger.warning(
                "Reaped compliance assessments whose worker never finished them.",
                extra={
                    "extra_fields": {
                        "organization_id": str(organization_id),
                        "count": len(reaped),
                    }
                },
            )
        return reaped

    @staticmethod
    def failures_of(outcome: AssessmentOutcome) -> list[ControlResult]:
        """Every result that should become a finding."""
        return outcome.failures()

    @staticmethod
    def unassessed_by_control(outcome: AssessmentOutcome) -> dict[str, int]:
        """How many targets each control could not be evaluated on.

        What drives the "audit evidence missing" notification. A control
        with no evidence is neither passing nor failing, so without this
        it is simply absent from every report -- the shape of gap that
        gets discovered in the room rather than beforehand.
        """
        tally: dict[str, int] = {}
        for one in outcome.results:
            if one.status is ResultStatus.NOT_ASSESSED:
                tally[one.control_id] = tally.get(one.control_id, 0) + 1
        return tally

    @staticmethod
    def critical_failures(outcome: AssessmentOutcome) -> list[ControlResult]:
        """Failures on controls rated critical, for immediate notification."""
        return [one for one in outcome.failures() if one.severity is ControlSeverity.CRITICAL]


def target_from_payload(data: dict[str, Any], *, index: int = 0) -> Target:
    """Build a :class:`Target` from an API payload.

    Raises:
        ValidationError: If it names nothing to assess.
    """
    target_id = str(data.get("target_id") or "").strip()
    if not target_id:
        raise ValidationError(f"Target at position {index} needs a target_id.")
    return Target(
        target_id=target_id,
        target_type=str(data.get("target_type") or "asset"),
        name=data.get("name"),
        payload=dict(data.get("payload") or {}),
        evidence_id=data.get("evidence_id"),
    )


__all__ = ["AssessmentService", "target_from_payload"]
