"""EscalationService: policy evaluation, manual overrides, acknowledgement."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from shared_core.exceptions.conflict import ConflictError

from app.models.enums import EscalationStatus, IncidentPriority
from app.services.escalation import EscalationService
from app.services.sla import SlaService

pytestmark = pytest.mark.asyncio


async def _breach_a_clock(sla_service: SlaService, organization_id, incident_id) -> datetime:
    """Start clocks in the past and sweep, so at least one is breached.

    ``breached_at`` is stamped at sweep time, not at the clock's actual
    due date -- so the moment a caller learns of a breach is also the
    moment the escalation ladder's anchor starts counting from. Returns
    that sweep moment so a caller can evaluate far enough past it for a
    P1's first rung (due 15 minutes after anchor) to actually be due.
    """
    past = datetime.now(UTC) - timedelta(days=10)
    await sla_service.start_clocks(
        organization_id, incident_id, priority=IncidentPriority.P1_CRITICAL, now=past
    )
    sweep_moment = datetime.now(UTC)
    await sla_service.sweep(organization_id, now=sweep_moment)
    return sweep_moment


class TestEvaluateIncident:
    async def test_evaluating_an_incident_with_no_breach_fires_nothing(
        self, escalation_service: EscalationService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        fired = await escalation_service.evaluate_incident(
            organization_id, incident.id, priority=IncidentPriority.P1_CRITICAL
        )
        assert fired == []

    async def test_a_breached_sla_fires_the_first_rung(
        self,
        escalation_service: EscalationService,
        sla_service: SlaService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident(priority=IncidentPriority.P1_CRITICAL)
        anchor = await _breach_a_clock(sla_service, organization_id, incident.id)
        fired = await escalation_service.evaluate_incident(
            organization_id,
            incident.id,
            priority=IncidentPriority.P1_CRITICAL,
            now=anchor + timedelta(minutes=20),
        )
        assert len(fired) >= 1
        assert fired[0].level == 1

    async def test_a_second_evaluation_does_not_refire_the_same_rung(
        self,
        escalation_service: EscalationService,
        sla_service: SlaService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident(priority=IncidentPriority.P1_CRITICAL)
        anchor = await _breach_a_clock(sla_service, organization_id, incident.id)
        moment = anchor + timedelta(minutes=20)
        first = await escalation_service.evaluate_incident(
            organization_id, incident.id, priority=IncidentPriority.P1_CRITICAL, now=moment
        )
        second = await escalation_service.evaluate_incident(
            organization_id, incident.id, priority=IncidentPriority.P1_CRITICAL, now=moment
        )
        fired_levels = {row.level for row in first}
        assert not any(row.level in fired_levels for row in second)

    async def test_evaluating_increments_the_incident_escalation_count(
        self,
        escalation_service: EscalationService,
        sla_service: SlaService,
        organization_id,
        make_incident,
        incidents_repo,
    ) -> None:
        incident = await make_incident(priority=IncidentPriority.P1_CRITICAL)
        anchor = await _breach_a_clock(sla_service, organization_id, incident.id)
        await escalation_service.evaluate_incident(
            organization_id,
            incident.id,
            priority=IncidentPriority.P1_CRITICAL,
            now=anchor + timedelta(minutes=20),
        )
        refreshed = await incidents_repo.require_in_org(organization_id, incident.id)
        assert refreshed.escalation_count >= 1


class TestManualEscalation:
    async def test_escalate_manually_creates_a_triggered_row(
        self, escalation_service: EscalationService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        row = await escalation_service.escalate_manually(
            organization_id, incident.id, target_id="director-1", reason="Executive visibility"
        )
        assert row.status == str(EscalationStatus.TRIGGERED)
        assert row.escalate_to_id == "director-1"

    async def test_manual_escalation_level_is_one_past_whatever_already_fired(
        self,
        escalation_service: EscalationService,
        sla_service: SlaService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident(priority=IncidentPriority.P1_CRITICAL)
        anchor = await _breach_a_clock(sla_service, organization_id, incident.id)
        fired = await escalation_service.evaluate_incident(
            organization_id,
            incident.id,
            priority=IncidentPriority.P1_CRITICAL,
            now=anchor + timedelta(minutes=20),
        )
        highest = max(row.level for row in fired)
        manual = await escalation_service.escalate_manually(
            organization_id, incident.id, target_id="director-1", reason="visibility"
        )
        assert manual.level == highest + 1


class TestAcknowledgeAndCancel:
    async def test_acknowledge_moves_a_triggered_escalation_to_acknowledged(
        self, escalation_service: EscalationService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        created = await escalation_service.escalate_manually(
            organization_id, incident.id, target_id="director-1", reason="visibility"
        )
        acked = await escalation_service.acknowledge(organization_id, created.id)
        assert acked.status == str(EscalationStatus.ACKNOWLEDGED)
        assert acked.acknowledged_at is not None

    async def test_acknowledging_a_non_triggered_escalation_raises(
        self, escalation_service: EscalationService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        created = await escalation_service.escalate_manually(
            organization_id, incident.id, target_id="director-1", reason="visibility"
        )
        await escalation_service.acknowledge(organization_id, created.id)
        with pytest.raises(ConflictError):
            await escalation_service.acknowledge(organization_id, created.id)

    async def test_cancel_moves_a_triggered_escalation_to_cancelled(
        self, escalation_service: EscalationService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        created = await escalation_service.escalate_manually(
            organization_id, incident.id, target_id="director-1", reason="visibility"
        )
        cancelled = await escalation_service.cancel(
            organization_id, created.id, reason="false alarm"
        )
        assert cancelled.status == str(EscalationStatus.CANCELLED)
        assert cancelled.cancelled_reason == "false alarm"

    async def test_cancelling_an_acknowledged_escalation_raises(
        self, escalation_service: EscalationService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        created = await escalation_service.escalate_manually(
            organization_id, incident.id, target_id="director-1", reason="visibility"
        )
        await escalation_service.acknowledge(organization_id, created.id)
        with pytest.raises(ConflictError):
            await escalation_service.cancel(organization_id, created.id, reason="too late")

    async def test_list_for_incident_returns_every_escalation(
        self, escalation_service: EscalationService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        await escalation_service.escalate_manually(
            organization_id, incident.id, target_id="director-1", reason="visibility"
        )
        listed = await escalation_service.list_for_incident(organization_id, incident.id)
        assert len(listed) == 1
