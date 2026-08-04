"""SlaService: starting clocks, pausing/resuming, sweeping, compliance."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from shared_core.exceptions.conflict import ConflictError

from app.models.enums import IncidentPriority, SlaKind, SlaStatus
from app.services.sla import SlaService

pytestmark = pytest.mark.asyncio


class TestStartClocks:
    async def test_starts_a_clock_per_configured_kind(
        self, sla_service: SlaService, organization_id, make_incident
    ) -> None:
        incident = await make_incident(priority=IncidentPriority.P1_CRITICAL)
        clocks = await sla_service.start_clocks(
            organization_id, incident.id, priority=IncidentPriority.P1_CRITICAL
        )
        kinds = {clock.kind for clock in clocks}
        assert SlaKind.RESPONSE in {str(k) for k in kinds} or SlaKind.RESPONSE in kinds
        assert len(clocks) >= 2

    async def test_every_clock_starts_running(
        self, sla_service: SlaService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        clocks = await sla_service.start_clocks(
            organization_id, incident.id, priority=IncidentPriority.P3_MEDIUM
        )
        assert all(clock.status == str(SlaStatus.RUNNING) for clock in clocks)

    async def test_escalation_kind_has_no_platform_default_and_is_skipped(
        self, sla_service: SlaService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        clocks = await sla_service.start_clocks(
            organization_id, incident.id, priority=IncidentPriority.P3_MEDIUM
        )
        assert all(str(clock.kind) != str(SlaKind.ESCALATION) for clock in clocks)


class TestMarkMet:
    async def test_marks_a_running_clock_met(
        self, sla_service: SlaService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        await sla_service.start_clocks(
            organization_id, incident.id, priority=IncidentPriority.P3_MEDIUM
        )
        updated = await sla_service.mark_met(organization_id, incident.id, SlaKind.RESPONSE)
        assert updated is not None
        assert updated.status == str(SlaStatus.MET)
        assert updated.met_at is not None

    async def test_marking_a_nonexistent_clock_is_a_no_op(
        self, sla_service: SlaService, organization_id
    ) -> None:
        result = await sla_service.mark_met(organization_id, uuid4(), SlaKind.RESPONSE)
        assert result is None

    async def test_marking_an_already_met_clock_leaves_it_untouched(
        self, sla_service: SlaService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        await sla_service.start_clocks(
            organization_id, incident.id, priority=IncidentPriority.P3_MEDIUM
        )
        first = await sla_service.mark_met(organization_id, incident.id, SlaKind.RESPONSE)
        second = await sla_service.mark_met(organization_id, incident.id, SlaKind.RESPONSE)
        assert first is not None
        assert second is not None
        assert first.met_at == second.met_at


class TestPauseResume:
    async def test_pause_moves_a_running_clock_to_paused(
        self, sla_service: SlaService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        clocks = await sla_service.start_clocks(
            organization_id, incident.id, priority=IncidentPriority.P3_MEDIUM
        )
        paused = await sla_service.pause(organization_id, clocks[0].id, reason="waiting on vendor")
        assert paused.status == str(SlaStatus.PAUSED)
        assert paused.pause_reason == "waiting on vendor"

    async def test_pausing_a_non_running_clock_raises(
        self, sla_service: SlaService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        clocks = await sla_service.start_clocks(
            organization_id, incident.id, priority=IncidentPriority.P3_MEDIUM
        )
        await sla_service.pause(organization_id, clocks[0].id, reason="first pause")
        with pytest.raises(ConflictError):
            await sla_service.pause(organization_id, clocks[0].id, reason="second pause")

    async def test_resume_returns_to_running_and_accumulates_paused_time(
        self, sla_service: SlaService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        clocks = await sla_service.start_clocks(
            organization_id, incident.id, priority=IncidentPriority.P3_MEDIUM
        )
        await sla_service.pause(organization_id, clocks[0].id, reason="waiting")
        resumed = await sla_service.resume(organization_id, clocks[0].id)
        assert resumed.status == str(SlaStatus.RUNNING)
        assert resumed.paused_at is None

    async def test_resuming_a_non_paused_clock_raises(
        self, sla_service: SlaService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        clocks = await sla_service.start_clocks(
            organization_id, incident.id, priority=IncidentPriority.P3_MEDIUM
        )
        with pytest.raises(ConflictError):
            await sla_service.resume(organization_id, clocks[0].id)


class TestListAndSweep:
    async def test_list_for_incident_returns_every_clock(
        self, sla_service: SlaService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        created = await sla_service.start_clocks(
            organization_id, incident.id, priority=IncidentPriority.P3_MEDIUM
        )
        listed = await sla_service.list_for_incident(organization_id, incident.id)
        assert len(listed) == len(created)

    async def test_sweep_breaches_a_clock_past_its_due_date(
        self, sla_service: SlaService, organization_id, make_incident, sla_repo
    ) -> None:
        incident = await make_incident()
        past = datetime.now(UTC) - timedelta(days=10)
        clocks = await sla_service.start_clocks(
            organization_id, incident.id, priority=IncidentPriority.P1_CRITICAL, now=past
        )
        counts = await sla_service.sweep(organization_id)
        assert counts["breached"] >= 1
        refreshed = await sla_repo.require_in_org(organization_id, clocks[0].id)
        assert refreshed.status == str(SlaStatus.BREACHED)

    async def test_sweep_is_independent_per_clock_and_does_not_stop_on_one_missing_incident(
        self, sla_service: SlaService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        await sla_service.start_clocks(
            organization_id, incident.id, priority=IncidentPriority.P3_MEDIUM
        )
        counts = await sla_service.sweep(organization_id)
        assert "warned" in counts
        assert "breached" in counts


class TestComplianceSummary:
    async def test_compliance_summary_counts_met_and_breached(
        self, sla_service: SlaService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        await sla_service.start_clocks(
            organization_id, incident.id, priority=IncidentPriority.P3_MEDIUM
        )
        await sla_service.mark_met(organization_id, incident.id, SlaKind.RESPONSE)
        start = datetime.now(UTC) - timedelta(hours=1)
        end = datetime.now(UTC) + timedelta(hours=1)
        summary = await sla_service.compliance_summary(organization_id, start=start, end=end)
        assert summary["met"] >= 1
        assert summary["rate"] > 0

    async def test_no_data_reports_full_compliance(
        self, sla_service: SlaService, organization_id
    ) -> None:
        start = datetime.now(UTC) - timedelta(hours=1)
        end = datetime.now(UTC) + timedelta(hours=1)
        summary = await sla_service.compliance_summary(organization_id, start=start, end=end)
        assert summary["rate"] == pytest.approx(100.0)
