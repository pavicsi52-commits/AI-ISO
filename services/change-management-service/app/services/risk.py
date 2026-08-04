"""Recording and overriding a change's risk assessment.

Wraps ``app/risk/engine.py`` with the database, the clock, and the
change lifecycle: the first assessment is what actually moves a change
from ``SUBMITTED`` through ``RISK_ASSESSMENT`` to ``PENDING_APPROVAL``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.logging.logger import get_logger

from app.changes.engine import requires_cab_review, validate_transition
from app.events.change_events import SOURCE_SERVICE, RiskAssessmentCompletedEvent
from app.models.enums import (
    ChangeStatus,
    RiskLevel,
    RiskLikelihood,
    change_status_of,
    risk_level_of,
)
from app.models.risk import ChangeRiskAssessment
from app.repositories.change import ChangeRequestRepository
from app.repositories.risk import ChangeRiskAssessmentRepository
from app.risk.engine import (
    RiskDimensions,
    approval_recommendation_for,
    automated_score,
    effective_risk_level,
    risk_level_for,
)
from app.types import EventPublisher

logger = get_logger("app.services.risk")

_ASSESSABLE_STATUSES = frozenset({ChangeStatus.SUBMITTED, ChangeStatus.RISK_ASSESSMENT})


class RiskService:
    """Risk assessment: scoring, recording, and manual override."""

    def __init__(
        self,
        assessments: ChangeRiskAssessmentRepository,
        changes: ChangeRequestRepository,
        *,
        publish_event: EventPublisher | None = None,
        standard_change_requires_cab: bool = False,
    ) -> None:
        self._assessments = assessments
        self._changes = changes
        self._publish = publish_event
        self._standard_change_requires_cab = standard_change_requires_cab

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def assess(
        self,
        organization_id: UUID,
        change_id: UUID,
        *,
        likelihood: RiskLikelihood,
        dimensions: RiskDimensions,
        assessed_by: str | None = None,
        manual_override: RiskLevel | None = None,
        override_reason: str | None = None,
        override_by: str | None = None,
        now: datetime | None = None,
    ) -> ChangeRiskAssessment:
        """Score and record a risk assessment, advancing the change past it.

        Raises:
            ConflictError: If the change is not in a status a risk
                assessment may run against.
        """
        moment = now or datetime.now(UTC)
        stored = await self._changes.require_in_org(organization_id, change_id)
        current = change_status_of(stored.status)
        if current not in _ASSESSABLE_STATUSES:
            raise ConflictError(
                f"{stored.reference} is {current!s}; a risk assessment cannot run against it."
            )

        impact = dimensions.worst()
        score = automated_score(likelihood=likelihood, impact=impact, dimensions=dimensions)
        automated_level = risk_level_for(score)
        effective_level = effective_risk_level(automated=automated_level, override=manual_override)
        recommendation = approval_recommendation_for(effective_level, stored.change_type)

        created = await self._assessments.create(
            ChangeRiskAssessment(
                organization_id=organization_id,
                change_id=change_id,
                likelihood=likelihood,
                impact=impact,
                technical_risk=dimensions.technical,
                business_risk=dimensions.business,
                operational_risk=dimensions.operational,
                security_risk=dimensions.security,
                compliance_risk=dimensions.compliance,
                dependency_risk=dimensions.dependency,
                automated_score=score,
                risk_level=automated_level,
                manual_override=manual_override,
                override_reason=override_reason,
                override_by=override_by,
                approval_recommendation=recommendation,
                assessed_by=assessed_by,
                assessed_at=moment,
            )
        )

        if current is ChangeStatus.SUBMITTED:
            validate_transition(current, ChangeStatus.RISK_ASSESSMENT)
            stored.status = ChangeStatus.RISK_ASSESSMENT
        validate_transition(change_status_of(stored.status), ChangeStatus.PENDING_APPROVAL)
        stored.risk_level = effective_level
        stored.cab_required = requires_cab_review(
            risk_level=effective_level,
            change_type=stored.change_type,
            standard_change_requires_cab=self._standard_change_requires_cab,
        )
        stored.status = ChangeStatus.PENDING_APPROVAL
        await self._changes.update(stored)

        await self._publish_event(
            RiskAssessmentCompletedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "change_id": str(change_id),
                    "risk_level": str(effective_level),
                    "cab_required": stored.cab_required,
                },
            )
        )
        return created

    async def override(
        self,
        organization_id: UUID,
        assessment_id: UUID,
        *,
        override: RiskLevel,
        reason: str,
        by: str,
    ) -> ChangeRiskAssessment:
        """Override a recorded assessment's banding, and recompute the change's own.

        Raises:
            NotFoundError: If the assessment does not exist here, or is
                not the change's most recent one -- overriding a
                superseded assessment would change a historical record
                nothing else still reads from.
        """
        row = await self._require_latest(organization_id, assessment_id)
        row.manual_override = override
        row.override_reason = reason
        row.override_by = by
        updated = await self._assessments.update(row)

        stored = await self._changes.require_in_org(organization_id, row.change_id)
        effective_level = effective_risk_level(
            automated=risk_level_of(row.risk_level), override=override
        )
        stored.risk_level = effective_level
        stored.cab_required = requires_cab_review(
            risk_level=effective_level,
            change_type=stored.change_type,
            standard_change_requires_cab=self._standard_change_requires_cab,
        )
        await self._changes.update(stored)
        return updated

    async def _require_latest(
        self, organization_id: UUID, assessment_id: UUID
    ) -> ChangeRiskAssessment:
        row = await self._assessments.require_by_id(assessment_id)
        if row.organization_id != organization_id:
            raise NotFoundError(f"No risk assessment with id {assessment_id} in this organization.")
        latest = await self._assessments.latest_for_change(organization_id, row.change_id)
        if latest is None or latest.id != row.id:
            raise NotFoundError(
                f"Risk assessment {assessment_id} is not the most recent for its change."
            )
        return row

    async def list_for_change(
        self, organization_id: UUID, change_id: UUID
    ) -> list[ChangeRiskAssessment]:
        """Every assessment for one change, in the order they were recorded."""
        return await self._assessments.list_for_change(organization_id, change_id)


__all__ = ["RiskService"]
