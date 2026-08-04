"""RiskService: scoring, recording, and overriding a change's risk assessment.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from tests.conftest import soon

from app.models.enums import ChangeStatus, ChangeType, RiskImpact, RiskLevel, RiskLikelihood
from app.models.risk import ChangeRiskAssessment
from app.risk.engine import RiskDimensions
from app.services.change import ChangeService
from app.services.risk import RiskService

pytestmark = pytest.mark.asyncio


def _uniform(impact: RiskImpact) -> RiskDimensions:
    """Six risk dimensions all reading the same impact."""
    return RiskDimensions(
        technical=impact,
        business=impact,
        operational=impact,
        security=impact,
        compliance=impact,
        dependency=impact,
    )


class TestAssess:
    async def test_wrong_status_raises_conflict_error(
        self, risk_service: RiskService, organization_id, make_change
    ) -> None:
        created = await make_change()
        with pytest.raises(ConflictError):
            await risk_service.assess(
                organization_id,
                created.id,
                likelihood=RiskLikelihood.POSSIBLE,
                dimensions=_uniform(RiskImpact.MINOR),
            )

    async def test_rare_and_minimal_dimensions_score_low_risk_without_cab(
        self, risk_service: RiskService, change_service: ChangeService, organization_id, make_change
    ) -> None:
        created = await make_change()
        await change_service.submit(organization_id, created.id)
        await risk_service.assess(
            organization_id,
            created.id,
            likelihood=RiskLikelihood.RARE,
            dimensions=_uniform(RiskImpact.MINIMAL),
        )
        updated = await change_service.get(organization_id, created.id)
        assert updated.risk_level == RiskLevel.LOW
        assert updated.cab_required is False
        assert updated.status == ChangeStatus.PENDING_APPROVAL

    async def test_possible_and_minor_dimensions_score_medium_risk_without_cab(
        self, risk_service: RiskService, change_service: ChangeService, organization_id, make_change
    ) -> None:
        created = await make_change()
        await change_service.submit(organization_id, created.id)
        await risk_service.assess(
            organization_id,
            created.id,
            likelihood=RiskLikelihood.POSSIBLE,
            dimensions=_uniform(RiskImpact.MINOR),
        )
        updated = await change_service.get(organization_id, created.id)
        assert updated.risk_level == RiskLevel.MEDIUM
        assert updated.cab_required is False

    async def test_moderate_dimensions_score_high_risk_requiring_cab_on_a_normal_change(
        self, risk_service: RiskService, change_service: ChangeService, organization_id, make_change
    ) -> None:
        created = await make_change()
        await change_service.submit(organization_id, created.id)
        await risk_service.assess(
            organization_id,
            created.id,
            likelihood=RiskLikelihood.POSSIBLE,
            dimensions=_uniform(RiskImpact.MODERATE),
        )
        updated = await change_service.get(organization_id, created.id)
        assert updated.risk_level == RiskLevel.HIGH
        assert updated.cab_required is True

    async def test_almost_certain_and_severe_dimensions_score_critical_risk_requiring_cab(
        self, risk_service: RiskService, change_service: ChangeService, organization_id, make_change
    ) -> None:
        created = await make_change()
        await change_service.submit(organization_id, created.id)
        await risk_service.assess(
            organization_id,
            created.id,
            likelihood=RiskLikelihood.ALMOST_CERTAIN,
            dimensions=_uniform(RiskImpact.SEVERE),
        )
        updated = await change_service.get(organization_id, created.id)
        assert updated.risk_level == RiskLevel.CRITICAL
        assert updated.cab_required is True

    async def test_a_single_severe_dimension_dominates_the_rest(
        self, risk_service: RiskService, change_service: ChangeService, organization_id, make_change
    ) -> None:
        created = await make_change()
        await change_service.submit(organization_id, created.id)
        dimensions = RiskDimensions(
            technical=RiskImpact.SEVERE,
            business=RiskImpact.MINIMAL,
            operational=RiskImpact.MINIMAL,
            security=RiskImpact.MINIMAL,
            compliance=RiskImpact.MINIMAL,
            dependency=RiskImpact.MINIMAL,
        )
        await risk_service.assess(
            organization_id, created.id, likelihood=RiskLikelihood.RARE, dimensions=dimensions
        )
        updated = await change_service.get(organization_id, created.id)
        assert updated.risk_level == RiskLevel.CRITICAL

    async def test_standard_change_never_requires_cab_even_at_critical_risk(
        self, risk_service: RiskService, change_service: ChangeService, organization_id, make_change
    ) -> None:
        created = await make_change(change_type=ChangeType.STANDARD)
        await change_service.submit(organization_id, created.id)
        await risk_service.assess(
            organization_id,
            created.id,
            likelihood=RiskLikelihood.ALMOST_CERTAIN,
            dimensions=_uniform(RiskImpact.SEVERE),
        )
        updated = await change_service.get(organization_id, created.id)
        assert updated.risk_level == RiskLevel.CRITICAL
        assert updated.cab_required is False

    async def test_emergency_change_never_requires_cab_even_at_critical_risk(
        self, risk_service: RiskService, change_service: ChangeService, organization_id, make_change
    ) -> None:
        created = await make_change(change_type=ChangeType.EMERGENCY)
        await change_service.submit(organization_id, created.id)
        await risk_service.assess(
            organization_id,
            created.id,
            likelihood=RiskLikelihood.ALMOST_CERTAIN,
            dimensions=_uniform(RiskImpact.SEVERE),
        )
        updated = await change_service.get(organization_id, created.id)
        assert updated.risk_level == RiskLevel.CRITICAL
        assert updated.cab_required is False

    async def test_assessing_from_risk_assessment_status_still_reaches_pending_approval(
        self, risk_service: RiskService, change_service: ChangeService, organization_id, make_change
    ) -> None:
        created = await make_change()
        await change_service.submit(organization_id, created.id)
        await change_service.transition(
            organization_id, created.id, target=ChangeStatus.RISK_ASSESSMENT
        )
        await risk_service.assess(
            organization_id,
            created.id,
            likelihood=RiskLikelihood.POSSIBLE,
            dimensions=_uniform(RiskImpact.MINOR),
        )
        updated = await change_service.get(organization_id, created.id)
        assert updated.status == ChangeStatus.PENDING_APPROVAL

    async def test_publishes_risk_assessment_completed_event(
        self,
        risk_service: RiskService,
        change_service: ChangeService,
        organization_id,
        make_change,
        publisher,
    ) -> None:
        created = await make_change()
        await change_service.submit(organization_id, created.id)
        await risk_service.assess(
            organization_id,
            created.id,
            likelihood=RiskLikelihood.POSSIBLE,
            dimensions=_uniform(RiskImpact.MINOR),
        )
        assert "RiskAssessmentCompleted" in publisher.names

    async def test_reassessing_an_already_assessed_change_raises_conflict_error(
        self, risk_service: RiskService, organization_id, make_assessed_change
    ) -> None:
        change = await make_assessed_change()
        with pytest.raises(ConflictError):
            await risk_service.assess(
                organization_id,
                change.id,
                likelihood=RiskLikelihood.POSSIBLE,
                dimensions=_uniform(RiskImpact.MINOR),
            )


class TestOverride:
    async def test_recomputes_the_changes_effective_level_and_cab_requirement(
        self,
        risk_service: RiskService,
        change_service: ChangeService,
        organization_id,
        make_assessed_change,
    ) -> None:
        change = await make_assessed_change()  # MEDIUM, CAB not required
        assessments = await risk_service.list_for_change(organization_id, change.id)
        overridden = await risk_service.override(
            organization_id,
            assessments[0].id,
            override=RiskLevel.CRITICAL,
            reason="Reassessed after a related outage",
            by="reviewer-1",
        )
        assert overridden.manual_override == RiskLevel.CRITICAL
        assert overridden.override_reason == "Reassessed after a related outage"
        assert overridden.override_by == "reviewer-1"
        updated = await change_service.get(organization_id, change.id)
        assert updated.risk_level == RiskLevel.CRITICAL
        assert updated.cab_required is True

    async def test_raises_not_found_for_a_missing_assessment(
        self, risk_service: RiskService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await risk_service.override(
                organization_id, uuid4(), override=RiskLevel.HIGH, reason="x", by="reviewer-1"
            )

    async def test_raises_not_found_for_an_assessment_in_another_organization(
        self, risk_service: RiskService, organization_id, make_assessed_change
    ) -> None:
        change = await make_assessed_change()
        assessments = await risk_service.list_for_change(organization_id, change.id)
        with pytest.raises(NotFoundError):
            await risk_service.override(
                uuid4(), assessments[0].id, override=RiskLevel.HIGH, reason="x", by="reviewer-1"
            )

    async def test_raises_not_found_for_a_superseded_assessment(
        self, risk_service: RiskService, risk_repo, organization_id, make_assessed_change
    ) -> None:
        change = await make_assessed_change()
        first = (await risk_service.list_for_change(organization_id, change.id))[0]
        await risk_repo.create(
            ChangeRiskAssessment(
                organization_id=organization_id,
                change_id=change.id,
                likelihood=RiskLikelihood.POSSIBLE,
                impact=RiskImpact.MINOR,
                technical_risk=RiskImpact.MINOR,
                business_risk=RiskImpact.MINOR,
                operational_risk=RiskImpact.MINOR,
                security_risk=RiskImpact.MINOR,
                compliance_risk=RiskImpact.MINOR,
                dependency_risk=RiskImpact.MINOR,
                automated_score=0.25,
                risk_level=RiskLevel.MEDIUM,
                approval_recommendation="Standard approval chain, CAB review not required.",
                assessed_at=soon(hours=1),
            )
        )
        with pytest.raises(NotFoundError):
            await risk_service.override(
                organization_id, first.id, override=RiskLevel.HIGH, reason="x", by="reviewer-1"
            )


class TestListForChange:
    async def test_lists_every_assessment_recorded_for_the_change(
        self, risk_service: RiskService, organization_id, make_assessed_change
    ) -> None:
        change = await make_assessed_change()
        found = await risk_service.list_for_change(organization_id, change.id)
        assert len(found) == 1
        assert found[0].change_id == change.id

    async def test_empty_for_a_change_never_assessed(
        self, risk_service: RiskService, organization_id, make_change
    ) -> None:
        created = await make_change()
        found = await risk_service.list_for_change(organization_id, created.id)
        assert found == []
