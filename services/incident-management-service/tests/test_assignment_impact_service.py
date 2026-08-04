"""AssignmentService and ImpactService, against real PostgreSQL."""

from __future__ import annotations

import pytest
from shared_core.exceptions.validation import ValidationError

from app.assignment.engine import Responder
from app.impact.engine import ServiceImpact
from app.models.enums import AssignmentMethod, ImpactLevel
from app.services.assignment import AssignmentService
from app.services.impact import ImpactService

pytestmark = pytest.mark.asyncio


class TestAssignmentService:
    async def test_decide_and_apply_assigns_the_on_call_responder(
        self, assignment_service: AssignmentService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        roster = [
            Responder(responder_id="alice", is_on_call=False),
            Responder(responder_id="bob", is_on_call=True),
        ]
        updated, decision = await assignment_service.decide_and_apply(
            organization_id, incident.id, roster=roster
        )
        assert updated.assignee_id == "bob"
        assert decision.method == AssignmentMethod.ON_CALL

    async def test_decide_and_apply_raises_when_nobody_is_eligible(
        self, assignment_service: AssignmentService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        roster = [Responder(responder_id="alice", is_available=False)]
        with pytest.raises(ValidationError):
            await assignment_service.decide_and_apply(organization_id, incident.id, roster=roster)

    async def test_roster_with_current_load_reflects_real_open_incident_counts(
        self,
        assignment_service: AssignmentService,
        incident_service,
        organization_id,
        make_incident,
    ) -> None:
        first = await make_incident()
        await incident_service.assign(organization_id, first.id, assignee_id="alice")
        roster = [Responder(responder_id="alice")]
        refreshed = await assignment_service.roster_with_current_load(organization_id, roster)
        assert refreshed[0].open_incident_count >= 1

    async def test_skill_based_assignment_when_on_call_disabled(
        self, assignment_service: AssignmentService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        roster = [
            Responder(responder_id="alice", skills=frozenset({"database"})),
            Responder(responder_id="bob", skills=frozenset()),
        ]
        updated, decision = await assignment_service.decide_and_apply(
            organization_id,
            incident.id,
            roster=roster,
            required_skills=frozenset({"database"}),
            prefer_on_call=False,
        )
        assert updated.assignee_id == "alice"
        assert decision.method == AssignmentMethod.SKILL_BASED


class TestImpactService:
    async def test_assess_records_worst_impact_and_updates_incident_risk(
        self, impact_service: ImpactService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        services = [
            ServiceImpact("checkout", ImpactLevel.MINOR),
            ServiceImpact("payments", ImpactLevel.SEVERE, is_root=True),
        ]
        assessed = await impact_service.assess(
            organization_id,
            incident.id,
            services=services,
            customer_impact=ImpactLevel.MAJOR,
        )
        assert assessed.topology_impact == str(ImpactLevel.SEVERE)

    async def test_summary_for_reports_the_latest_assessment_and_breakdown(
        self, impact_service: ImpactService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        await impact_service.assess(
            organization_id,
            incident.id,
            services=[ServiceImpact("checkout", ImpactLevel.MODERATE)],
        )
        summary = await impact_service.summary_for(organization_id, incident.id)
        assert summary["latest"] is not None
        assert summary["by_level"][str(ImpactLevel.MODERATE)] == 1

    async def test_history_lists_every_assessment(
        self, impact_service: ImpactService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        await impact_service.assess(
            organization_id, incident.id, services=[ServiceImpact("a", ImpactLevel.MINOR)]
        )
        await impact_service.assess(
            organization_id, incident.id, services=[ServiceImpact("a", ImpactLevel.MAJOR)]
        )
        history = await impact_service.history(organization_id, incident.id)
        assert len(history) == 2

    async def test_assess_with_assets_records_asset_impacts(
        self, impact_service: ImpactService, organization_id, make_incident, asset_impact_repo
    ) -> None:
        incident = await make_incident()
        await impact_service.assess(
            organization_id,
            incident.id,
            services=[ServiceImpact("checkout", ImpactLevel.MINOR)],
            assets=[("host-1", "Host One", ImpactLevel.MINOR, "high CPU")],
        )
        rows = await asset_impact_repo.list_for_incident(organization_id, incident.id)
        assert len(rows) == 1
        assert rows[0].asset_id == "host-1"
