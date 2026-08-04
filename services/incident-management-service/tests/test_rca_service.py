"""RootCauseService and ProblemService, against real PostgreSQL."""

from __future__ import annotations

import pytest
from shared_core.exceptions.conflict import ConflictError

from app.models.enums import ProblemStatus, RcaMethod
from app.services.rca import ProblemService, RootCauseService

pytestmark = pytest.mark.asyncio


class TestRootCauseService:
    async def test_record_creates_a_finding(
        self, root_cause_service: RootCauseService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        finding = await root_cause_service.record(
            organization_id, incident.id, method=RcaMethod.MANUAL, summary="Bad deploy"
        )
        assert finding.summary == "Bad deploy"
        assert finding.is_confirmed is False

    async def test_recording_a_confirmed_finding_sets_the_incident_root_cause(
        self, root_cause_service: RootCauseService, organization_id, make_incident, incidents_repo
    ) -> None:
        incident = await make_incident()
        finding = await root_cause_service.record(
            organization_id,
            incident.id,
            method=RcaMethod.MANUAL,
            summary="Bad deploy",
            is_confirmed=True,
            recorded_by="alice",
        )
        refreshed = await incidents_repo.require_in_org(organization_id, incident.id)
        assert refreshed.root_cause_id == finding.id

    async def test_confirm_upgrades_a_hypothesis(
        self, root_cause_service: RootCauseService, organization_id, make_incident, incidents_repo
    ) -> None:
        incident = await make_incident()
        finding = await root_cause_service.record(
            organization_id, incident.id, method=RcaMethod.AI_ASSISTED, summary="Maybe memory leak"
        )
        confirmed = await root_cause_service.confirm(
            organization_id, finding.id, confirmed_by="bob"
        )
        assert confirmed.is_confirmed is True
        assert confirmed.confirmed_by == "bob"
        refreshed = await incidents_repo.require_in_org(organization_id, incident.id)
        assert refreshed.root_cause_id == finding.id

    async def test_every_finding_is_kept_not_just_the_latest(
        self, root_cause_service: RootCauseService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        await root_cause_service.record(
            organization_id, incident.id, method=RcaMethod.MANUAL, summary="First theory"
        )
        await root_cause_service.record(
            organization_id, incident.id, method=RcaMethod.MANUAL, summary="Revised theory"
        )
        findings = await root_cause_service.list_for_incident(organization_id, incident.id)
        assert len(findings) == 2


class TestProblemService:
    async def test_create_generates_a_reference_and_links_incidents(
        self, problem_service: ProblemService, organization_id, make_incident, incidents_repo
    ) -> None:
        incident = await make_incident()
        problem = await problem_service.create(
            organization_id, title="Recurring OOM", incident_ids=[incident.id]
        )
        assert problem.reference.startswith("PRB-")
        assert problem.incident_count == 1
        refreshed = await incidents_repo.require_in_org(organization_id, incident.id)
        assert refreshed.problem_id == problem.id

    async def test_reference_sequence_increments_independently_of_incidents(
        self, problem_service: ProblemService, organization_id
    ) -> None:
        first = await problem_service.create(organization_id, title="A")
        second = await problem_service.create(organization_id, title="B")
        first_seq = int(first.reference.rsplit("-", 1)[1])
        second_seq = int(second.reference.rsplit("-", 1)[1])
        assert second_seq == first_seq + 1

    async def test_create_publishes_problem_created_event(
        self, problem_service: ProblemService, organization_id, publisher
    ) -> None:
        await problem_service.create(organization_id, title="Recurring OOM")
        assert "ProblemCreated" in publisher.names

    async def test_link_incident_attaches_one_more_incident(
        self, problem_service: ProblemService, organization_id, make_incident, incidents_repo
    ) -> None:
        problem = await problem_service.create(organization_id, title="Recurring OOM")
        incident = await make_incident()
        updated = await problem_service.link_incident(organization_id, problem.id, incident.id)
        assert updated.incident_count == 1
        refreshed = await incidents_repo.require_in_org(organization_id, incident.id)
        assert refreshed.problem_id == problem.id

    async def test_linking_the_same_incident_twice_does_not_duplicate(
        self, problem_service: ProblemService, organization_id, make_incident
    ) -> None:
        problem = await problem_service.create(organization_id, title="Recurring OOM")
        incident = await make_incident()
        await problem_service.link_incident(organization_id, problem.id, incident.id)
        updated = await problem_service.link_incident(organization_id, problem.id, incident.id)
        assert updated.incident_count == 1

    async def test_transition_to_resolved_without_a_fix_raises(
        self, problem_service: ProblemService, organization_id
    ) -> None:
        problem = await problem_service.create(organization_id, title="Recurring OOM")
        with pytest.raises(ConflictError):
            await problem_service.transition(
                organization_id, problem.id, target=ProblemStatus.RESOLVED
            )

    async def test_transition_to_resolved_with_a_fix_succeeds(
        self, problem_service: ProblemService, organization_id
    ) -> None:
        problem = await problem_service.create(organization_id, title="Recurring OOM")
        updated = await problem_service.transition(
            organization_id,
            problem.id,
            target=ProblemStatus.RESOLVED,
            permanent_fix="Increased heap size",
        )
        assert updated.status == ProblemStatus.RESOLVED
        assert updated.resolved_at is not None

    async def test_record_known_error_moves_problem_to_known_error_status(
        self, problem_service: ProblemService, organization_id
    ) -> None:
        problem = await problem_service.create(organization_id, title="Recurring OOM")
        known_error = await problem_service.record_known_error(
            organization_id,
            problem.id,
            title="OOM under load",
            root_cause_summary="Leaky cache",
            workaround="Restart nightly",
        )
        assert known_error.is_active is True
        refreshed = await problem_service.get(organization_id, problem.id)
        assert refreshed.status == ProblemStatus.KNOWN_ERROR

    async def test_retire_known_error_marks_it_inactive(
        self, problem_service: ProblemService, organization_id
    ) -> None:
        problem = await problem_service.create(organization_id, title="Recurring OOM")
        known_error = await problem_service.record_known_error(
            organization_id, problem.id, title="OOM", root_cause_summary="Leak"
        )
        retired = await problem_service.retire_known_error(organization_id, known_error.id)
        assert retired.is_active is False
        assert retired.retired_at is not None

    async def test_list_active_known_errors_excludes_retired(
        self, problem_service: ProblemService, organization_id
    ) -> None:
        problem = await problem_service.create(organization_id, title="Recurring OOM")
        active = await problem_service.record_known_error(
            organization_id, problem.id, title="Still open", root_cause_summary="x"
        )
        retired = await problem_service.record_known_error(
            organization_id, problem.id, title="Fixed now", root_cause_summary="y"
        )
        await problem_service.retire_known_error(organization_id, retired.id)
        listed = await problem_service.list_active_known_errors(organization_id)
        ids = {one.id for one in listed}
        assert active.id in ids
        assert retired.id not in ids

    async def test_list_problems_filters_by_status(
        self, problem_service: ProblemService, organization_id
    ) -> None:
        await problem_service.create(organization_id, title="Open one")
        found = await problem_service.list_problems(organization_id, status=ProblemStatus.OPEN)
        assert len(found) >= 1
        assert all(one.status == str(ProblemStatus.OPEN) for one in found)
