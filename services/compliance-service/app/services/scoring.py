"""Computing, storing, and trending compliance scores."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from shared_core.logging.logger import get_logger

from app.events.compliance_events import SOURCE_SERVICE, ComplianceScoreUpdatedEvent
from app.models.enums import (
    ControlSeverity,
    ResultStatus,
    ScoreScope,
    grade_for,
    result_status_of,
)
from app.models.governance import ComplianceScore
from app.repositories.catalogue import ControlRepository, FrameworkRepository
from app.repositories.governance import ScoreRepository
from app.repositories.runs import AssessmentRepository, ResultRepository
from app.scoring.engine import (
    ScoreBreakdown,
    ScoredResult,
    combine_framework_scores,
    compute_score,
    coverage_of,
    delta_of,
    score_by_framework,
    score_by_target,
    trend_of,
)
from app.types import EventPublisher

logger = get_logger("app.services.scoring")


class ScoringService:
    """Turns results into scores, and keeps them for trending."""

    def __init__(
        self,
        scores: ScoreRepository,
        results: ResultRepository,
        assessments: AssessmentRepository,
        frameworks: FrameworkRepository,
        controls: ControlRepository,
        *,
        publish_event: EventPublisher | None = None,
        minimum_controls: int = 1,
    ) -> None:
        self._scores = scores
        self._results = results
        self._assessments = assessments
        self._frameworks = frameworks
        self._controls = controls
        self._publish = publish_event
        self._minimum_controls = minimum_controls

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def _scored_results(
        self, organization_id: UUID, assessment_id: UUID, *, limit: int = 20_000
    ) -> list[ScoredResult]:
        """Project one run's results into the scorer's input shape.

        Control severities are fetched in one batch rather than per
        result. A run of ten thousand results would otherwise issue ten
        thousand queries to look up a handful of distinct controls --
        which is how scoring comes to take longer than the assessment it
        is scoring.
        """
        rows = await self._results.list_for_assessment(organization_id, assessment_id, limit=limit)
        control_ids = list({one.control_id for one in rows})
        controls = await self._controls.list_by_ids(organization_id, control_ids)
        severity_of = {one.id: ControlSeverity(str(one.severity)) for one in controls}
        return [
            ScoredResult(
                control_id=str(one.control_id),
                status=result_status_of(one.status),
                severity=severity_of.get(one.control_id, ControlSeverity.MEDIUM),
                framework_id=str(one.framework_id) if one.framework_id else None,
                target_id=one.target_id,
            )
            for one in rows
        ]

    async def score_assessment(
        self,
        organization_id: UUID,
        assessment_id: UUID,
        *,
        actor_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Score one run overall and per framework, and store both.

        Stored rather than computed on demand, because a score is a
        historical fact: "what did we look like in Q3" cannot be
        recomputed later once controls have been reworded, scoped out, or
        retired. A dashboard that recomputes history rewrites it.
        """
        await self._assessments.require_in_org(organization_id, assessment_id)
        scored = await self._scored_results(organization_id, assessment_id)

        overall = compute_score(scored, minimum_controls=self._minimum_controls)
        per_framework = score_by_framework(scored, minimum_controls=self._minimum_controls)

        weights: dict[str, float] = {}
        for framework_id in per_framework:
            framework = await self._frameworks.require_in_org(organization_id, UUID(framework_id))
            weights[framework_id] = framework.weight

        combined = (
            combine_framework_scores(per_framework, weights) if per_framework else overall.score
        )
        coverage = coverage_of(scored)
        now = datetime.now(UTC)

        stored = await self._store(
            organization_id,
            scope=ScoreScope.OVERALL,
            scope_id=None,
            scope_name="Overall",
            breakdown=overall,
            assessment_id=assessment_id,
            computed_at=now,
            actor_id=actor_id,
            extra={"coverage": round(coverage, 2), "combined_framework_score": round(combined, 2)},
        )

        for framework_id, breakdown in per_framework.items():
            framework = await self._frameworks.require_in_org(organization_id, UUID(framework_id))
            await self._store(
                organization_id,
                scope=ScoreScope.FRAMEWORK,
                scope_id=framework_id,
                scope_name=framework.name,
                breakdown=breakdown,
                assessment_id=assessment_id,
                framework_id=UUID(framework_id),
                computed_at=now,
                actor_id=actor_id,
                extra={
                    "coverage": round(
                        coverage_of([one for one in scored if one.framework_id == framework_id]), 2
                    )
                },
            )

        await self._publish_event(
            ComplianceScoreUpdatedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "assessment_id": str(assessment_id),
                    "score": round(overall.score, 2),
                    "grade": str(overall.grade),
                    "coverage": round(coverage, 2),
                    "delta": stored.delta,
                    "publishable": overall.publishable,
                },
            )
        )

        return {
            "overall": overall.as_dict(),
            "coverage": round(coverage, 2),
            "combined_framework_score": round(combined, 2),
            "by_framework": {key: value.as_dict() for key, value in per_framework.items()},
            "delta": stored.delta,
        }

    async def _store(
        self,
        organization_id: UUID,
        *,
        scope: ScoreScope,
        scope_id: str | None,
        scope_name: str | None,
        breakdown: ScoreBreakdown,
        computed_at: datetime,
        assessment_id: UUID | None = None,
        framework_id: UUID | None = None,
        actor_id: UUID | None = None,
        extra: dict[str, Any] | None = None,
    ) -> ComplianceScore:
        """Persist one score, with its movement against the last one."""
        previous = await self._scores.latest(organization_id, scope=scope, scope_id=scope_id)
        previous_score = previous.score if previous is not None else None
        return await self._scores.create(
            ComplianceScore(
                organization_id=organization_id,
                scope=scope,
                scope_id=scope_id,
                scope_name=scope_name,
                framework_id=framework_id,
                assessment_id=assessment_id,
                score=round(breakdown.score, 2),
                grade=breakdown.grade,
                weighted_score=round(breakdown.weighted_score, 2),
                raw_pass_rate=round(breakdown.raw_pass_rate, 2),
                controls_total=breakdown.total,
                controls_passed=breakdown.passed,
                controls_failed=breakdown.failed + breakdown.warned,
                controls_excepted=breakdown.excepted,
                controls_not_applicable=breakdown.not_applicable,
                previous_score=previous_score,
                delta=delta_of(breakdown.score, previous_score),
                computed_at=computed_at,
                breakdown={**breakdown.as_dict(), **(extra or {})},
                created_by=actor_id,
            )
        )

    async def current(
        self,
        organization_id: UUID,
        *,
        scope: ScoreScope = ScoreScope.OVERALL,
        scope_id: str | None = None,
    ) -> dict[str, Any] | None:
        """The most recent score for one scope."""
        found = await self._scores.latest(organization_id, scope=scope, scope_id=scope_id)
        if found is None:
            return None
        return {
            "scope": str(found.scope),
            "scope_id": found.scope_id,
            "scope_name": found.scope_name,
            "score": found.score,
            "grade": str(found.grade),
            "raw_pass_rate": found.raw_pass_rate,
            "previous_score": found.previous_score,
            "delta": found.delta,
            "computed_at": found.computed_at.isoformat(),
            "breakdown": found.breakdown,
        }

    async def history(
        self,
        organization_id: UUID,
        *,
        scope: ScoreScope = ScoreScope.OVERALL,
        scope_id: str | None = None,
        days: int = 365,
    ) -> dict[str, Any]:
        """A scope's score over time, with its direction."""
        since = datetime.now(UTC) - timedelta(days=days)
        rows = await self._scores.history(
            organization_id, scope=scope, scope_id=scope_id, since=since
        )
        points = [(one.computed_at, one.score) for one in rows]
        return {
            "scope": str(scope),
            "scope_id": scope_id,
            "points": [{"at": moment.isoformat(), "score": value} for moment, value in points],
            "trend": trend_of(points),
            "first": points[0][1] if points else None,
            "latest": points[-1][1] if points else None,
        }

    async def framework_scores(
        self, organization_id: UUID, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        """The newest score for every framework."""
        rows = await self._scores.latest_per_scope(
            organization_id, scope=ScoreScope.FRAMEWORK, limit=limit
        )
        return [
            {
                "framework_id": one.scope_id,
                "framework_name": one.scope_name,
                "score": one.score,
                "grade": str(one.grade),
                "delta": one.delta,
                "computed_at": one.computed_at.isoformat(),
            }
            for one in rows
        ]

    async def score_targets(
        self,
        organization_id: UUID,
        assessment_id: UUID,
        *,
        limit: int = 200,
        actor_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Score every asset in one run, worst first.

        How remediation gets prioritised: the estate-wide number says
        whether there is a problem, and this says where to go.
        """
        scored = await self._scored_results(organization_id, assessment_id)
        per_target = score_by_target(scored, minimum_controls=self._minimum_controls)
        now = datetime.now(UTC)

        ranked = sorted(per_target.items(), key=lambda pair: pair[1].score)[:limit]
        for target_id, breakdown in ranked:
            await self._store(
                organization_id,
                scope=ScoreScope.ASSET,
                scope_id=target_id,
                scope_name=target_id,
                breakdown=breakdown,
                assessment_id=assessment_id,
                computed_at=now,
                actor_id=actor_id,
            )
        return [
            {
                "target_id": target_id,
                "score": round(breakdown.score, 2),
                "grade": str(breakdown.grade),
                "failed": breakdown.failed + breakdown.warned,
                "total": breakdown.total,
            }
            for target_id, breakdown in ranked
        ]

    @staticmethod
    def grade(score: float) -> str:
        """Band a numeric score for an executive summary."""
        return str(grade_for(score))

    @staticmethod
    def failing_statuses() -> list[str]:
        """The result statuses that count against a score."""
        return [str(ResultStatus.FAIL), str(ResultStatus.WARNING)]


__all__ = ["ScoringService"]
