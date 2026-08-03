"""Service-level tests against real PostgreSQL.

No mocked infrastructure. Where a test asserts something about
transaction lifetime it uses the real session factory, because the
SAVEPOINT the other fixtures run under does not roll back the way a real
request does -- see the conftest docstring.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessments.engine import ControlResult, Target
from app.models.enums import (
    AssessmentStatus,
    ControlSeverity,
    ControlStatus,
    EvidenceKind,
    EvidenceSource,
    FindingStatus,
    FrameworkStatus,
    ResultStatus,
)
from app.models.evidence import content_digest
from app.repositories.runs import EvidenceRepository
from app.rules.engine import Rule
from app.services.assessment import AssessmentService, target_from_payload
from app.services.catalogue import CatalogueService
from app.services.evidence import EvidenceService
from app.services.finding import FindingService
from app.services.governance import ExceptionService
from tests.conftest import MakeControlFn, RecordingPublisher, firewall_rule, soon, utcnow


class TestCatalogue:
    async def test_a_framework_and_its_controls_round_trip(
        self,
        catalogue_service: CatalogueService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework("iso")
        await make_control(framework.id, "A.1")
        await make_control(framework.id, "A.2")

        found = await catalogue_service.get_framework(organization_id, framework.id)
        assert found.slug == "iso"
        assert found.control_count == 2, "the denominator is recounted, not incremented"

    async def test_a_duplicate_framework_slug_is_refused(
        self, make_framework: MakeControlFn
    ) -> None:
        await make_framework("iso")
        with pytest.raises(ConflictError):
            await make_framework("iso")

    async def test_a_duplicate_control_code_in_one_framework_is_refused(
        self, make_framework: MakeControlFn, make_control: MakeControlFn
    ) -> None:
        framework = await make_framework()
        await make_control(framework.id, "A.1")
        with pytest.raises(ConflictError):
            await make_control(framework.id, "A.1")

    async def test_the_same_code_may_exist_in_two_frameworks(
        self, make_framework: MakeControlFn, make_control: MakeControlFn
    ) -> None:
        # ISO and NIST both have controls numbered from 1; uniqueness is
        # per framework, not per organization.
        first = await make_framework("iso")
        second = await make_framework("nist")
        await make_control(first.id, "1.1")
        await make_control(second.id, "1.1")

    async def test_a_control_rule_is_validated_before_it_replaces_the_old_one(
        self,
        catalogue_service: CatalogueService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # Writing the new rule and then finding it malformed would leave
        # the control with nothing evaluable while still flagged
        # automatable -- NOT_ASSESSED forever, while looking configured.
        framework = await make_framework()
        control = await make_control(framework.id, "A.1")

        with pytest.raises(ValidationError):
            await catalogue_service.set_control_rule(
                organization_id, control.id, Rule(name="empty")
            )

        found = await catalogue_service.get_control(organization_id, control.id)
        assert found.rule["checks"], "the original rule survived"

    async def test_a_control_cannot_be_mapped_to_itself(
        self,
        catalogue_service: CatalogueService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # A self-mapping counts the control twice in every coverage
        # calculation that follows the mapping graph.
        framework = await make_framework()
        control = await make_control(framework.id, "A.1")
        with pytest.raises(ValidationError, match="itself"):
            await catalogue_service.map_controls(
                organization_id,
                source_control_id=control.id,
                target_control_id=control.id,
            )

    async def test_a_mapping_is_visible_from_both_ends(
        self,
        catalogue_service: CatalogueService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # A caller asking "what else does this answer?" does not know or
        # care which side the mapping was authored from.
        first = await make_framework("iso")
        second = await make_framework("nist")
        source = await make_control(first.id, "A.9")
        target = await make_control(second.id, "AC-6")
        await catalogue_service.map_controls(
            organization_id, source_control_id=source.id, target_control_id=target.id
        )

        assert len(await catalogue_service.related_controls(organization_id, source.id)) == 1
        assert len(await catalogue_service.related_controls(organization_id, target.id)) == 1

    async def test_a_duplicate_mapping_is_refused(
        self,
        catalogue_service: CatalogueService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        first = await make_framework("iso")
        second = await make_framework("nist")
        source = await make_control(first.id, "A.9")
        target = await make_control(second.id, "AC-6")
        await catalogue_service.map_controls(
            organization_id, source_control_id=source.id, target_control_id=target.id
        )
        with pytest.raises(ConflictError):
            await catalogue_service.map_controls(
                organization_id, source_control_id=source.id, target_control_id=target.id
            )

    async def test_seeding_installs_the_shipped_catalogue_and_is_idempotent(
        self, catalogue_service: CatalogueService, organization_id: uuid.UUID
    ) -> None:
        seeded = await catalogue_service.seed_builtin(organization_id)
        assert len(seeded) == 5
        reason = "a framework sitting in draft is a framework that is not measuring anything"
        assert all(one.status == FrameworkStatus.ACTIVE for one in seeded), reason

        again = await catalogue_service.seed_builtin(organization_id)
        assert again == [], "re-seeding adds only what is missing"

    async def test_seeding_installs_the_cross_framework_mappings(
        self, catalogue_service: CatalogueService, organization_id: uuid.UUID
    ) -> None:
        # The mappings are what let one evaluation answer several
        # standards, which is the property that makes adding the next
        # framework cheap.
        await catalogue_service.seed_builtin(organization_id)
        controls = await catalogue_service.list_controls(organization_id, limit=500)
        ac6 = next(one for one in controls if one.code == "AC-6")
        assert await catalogue_service.related_controls(organization_id, ac6.id)

    async def test_a_builtin_framework_cannot_be_reworded(
        self, catalogue_service: CatalogueService, organization_id: uuid.UUID
    ) -> None:
        # Reporting against something that is not NIST while calling it
        # NIST is worse than not tracking it, because the report is
        # believed.
        seeded = await catalogue_service.seed_builtin(organization_id)
        with pytest.raises(ConflictError, match="ships with the platform"):
            await catalogue_service.update_framework(organization_id, seeded[0].id, name="Our NIST")

    async def test_a_builtin_control_keeps_its_wording_but_yields_its_status(
        self, catalogue_service: CatalogueService, organization_id: uuid.UUID
    ) -> None:
        # Status and ownership are statements about this organization's
        # programme, not about the standard.
        await catalogue_service.seed_builtin(organization_id)
        control = (await catalogue_service.list_controls(organization_id, limit=1))[0]

        with pytest.raises(ConflictError):
            await catalogue_service.update_control(organization_id, control.id, title="Reworded")
        updated = await catalogue_service.update_control(
            organization_id,
            control.id,
            status=ControlStatus.NOT_APPLICABLE,
            owner_id="team-platform",
        )
        assert catalogue_service.status_of(updated) is ControlStatus.NOT_APPLICABLE

    async def test_a_builtin_controls_rule_cannot_be_replaced(
        self, catalogue_service: CatalogueService, organization_id: uuid.UUID
    ) -> None:
        await catalogue_service.seed_builtin(organization_id)
        control = (await catalogue_service.list_controls(organization_id, limit=1))[0]
        with pytest.raises(ConflictError):
            await catalogue_service.set_control_rule(organization_id, control.id, firewall_rule())

    async def test_implementation_rate_excludes_scoped_out_controls(
        self,
        catalogue_service: CatalogueService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # A control formally scoped out is not outstanding work; counting
        # it makes a finished programme look permanently incomplete.
        framework = await make_framework()
        await make_control(framework.id, "A.1", status=ControlStatus.IMPLEMENTED)
        await make_control(framework.id, "A.2", status=ControlStatus.NOT_APPLICABLE)

        summary = await catalogue_service.implementation_summary(organization_id)
        assert summary["total"] == 2
        assert summary["applicable"] == 1
        assert summary["implementation_rate"] == 100.0

    async def test_archiving_a_framework_twice_is_refused(
        self,
        catalogue_service: CatalogueService,
        make_framework: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        await catalogue_service.archive_framework(organization_id, framework.id)
        with pytest.raises(ConflictError):
            await catalogue_service.archive_framework(organization_id, framework.id)

    async def test_another_organizations_framework_is_not_found(
        self, catalogue_service: CatalogueService, make_framework: MakeControlFn
    ) -> None:
        # Not a permission error: telling a caller it exists but belongs
        # to somebody else confirms the id, which is the one thing they
        # did not already know.
        framework = await make_framework()
        with pytest.raises(NotFoundError):
            await catalogue_service.get_framework(uuid.uuid4(), framework.id)


class TestEvidence:
    async def test_evidence_is_hashed_when_it_arrives(self, make_evidence: MakeControlFn) -> None:
        stored = await make_evidence("host-1", {"firewall": {"enabled": True}})
        assert stored.digest == content_digest({"firewall": {"enabled": True}})

    async def test_the_digest_is_independent_of_key_order(
        self, make_evidence: MakeControlFn
    ) -> None:
        # Verification failing for reasons that have nothing to do with
        # tampering trains people to ignore verification failures.
        first = await make_evidence("host-1", {"a": 1, "b": 2})
        second = await make_evidence("host-2", {"b": 2, "a": 1})
        assert first.digest == second.digest

    async def test_empty_evidence_is_refused(
        self, evidence_service: EvidenceService, organization_id: uuid.UUID
    ) -> None:
        # A record proving nothing makes a gap look filled, which is
        # worse than having no evidence at all.
        with pytest.raises(ValidationError, match="gap look filled"):
            await evidence_service.collect(
                organization_id,
                kind=EvidenceKind.CONFIGURATION_SNAPSHOT,
                source=EvidenceSource.MANUAL_UPLOAD,
                title="Nothing",
                payload={},
            )

    async def test_an_oversized_payload_is_refused_with_a_useful_message(
        self, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        service = EvidenceService(EvidenceRepository(db_session), max_payload_bytes=64)
        with pytest.raises(ValidationError, match="object storage"):
            await service.collect(
                organization_id,
                kind=EvidenceKind.CONFIGURATION_SNAPSHOT,
                source=EvidenceSource.MANUAL_UPLOAD,
                title="Huge",
                payload={"data": "x" * 500},
            )

    async def test_correction_supersedes_and_both_rows_survive(
        self,
        evidence_service: EvidenceService,
        make_evidence: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        original = await make_evidence("host-1", {"firewall": {"enabled": False}})
        replacement = await evidence_service.supersede(
            organization_id,
            original.id,
            payload={"firewall": {"enabled": True}},
            reason="The first collector read a stale cache.",
        )

        assert replacement.supersedes_id == original.id
        both = await evidence_service.list_evidence(organization_id, include_superseded=True)
        assert len(both) == 2
        current = await evidence_service.list_evidence(organization_id)
        assert len(current) == 1
        assert current[0].id == replacement.id

    async def test_a_superseded_row_still_verifies(
        self,
        evidence_service: EvidenceService,
        make_evidence: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # A corrected record whose predecessor no longer checks out is
        # not a correction, it is a gap.
        original = await make_evidence("host-1", {"v": 1})
        await evidence_service.supersede(organization_id, original.id, payload={"v": 2})
        stored = await evidence_service.get(organization_id, original.id)
        assert evidence_service.verify(stored) is True
        assert stored.is_superseded is True

    async def test_a_tampered_payload_fails_verification(
        self,
        evidence_service: EvidenceService,
        make_evidence: MakeControlFn,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        # Simulates a change that bypassed this service -- direct SQL, a
        # doctored backup restore -- which is exactly what a stored
        # checksum is for and what an application-level "immutable" flag
        # would miss.
        stored = await make_evidence("host-1", {"firewall": {"enabled": False}})
        stored.payload = {"firewall": {"enabled": True}}
        await db_session.flush()

        assert evidence_service.verify(stored) is False
        report = await evidence_service.verify_all(organization_id)
        assert report["failed"] == 1
        assert report["failures"][0]["recorded_digest"] != report["failures"][0]["computed_digest"]

    async def test_verify_all_includes_superseded_rows(
        self,
        evidence_service: EvidenceService,
        make_evidence: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # A tampered historical record is exactly what this is looking
        # for; excluding them would leave the largest and least-watched
        # part of the trail unchecked.
        original = await make_evidence("host-1", {"v": 1})
        await evidence_service.supersede(organization_id, original.id, payload={"v": 2})
        report = await evidence_service.verify_all(organization_id)
        assert report["checked"] == 2

    async def test_evidence_expires(
        self, make_evidence: MakeControlFn, evidence_service: EvidenceService
    ) -> None:
        stored = await make_evidence("host-1", validity_days=1)
        assert evidence_service.is_current(stored) is True
        assert evidence_service.is_current(stored, now=utcnow() + timedelta(days=2)) is False

    async def test_evidence_with_no_expiry_is_always_current(
        self, make_evidence: MakeControlFn, evidence_service: EvidenceService
    ) -> None:
        stored = await make_evidence("host-1")
        stored.expires_at = None
        assert evidence_service.is_current(stored) is True

    async def test_expiring_evidence_is_findable_before_it_lapses(
        self,
        make_evidence: MakeControlFn,
        evidence_service: EvidenceService,
        organization_id: uuid.UUID,
    ) -> None:
        await make_evidence("host-1", validity_days=5)
        assert await evidence_service.expiring_soon(organization_id, within_days=30)
        assert not await evidence_service.expiring_soon(organization_id, within_days=1)

    async def test_merged_evidence_lets_newer_snapshots_win(
        self,
        make_evidence: MakeControlFn,
        evidence_service: EvidenceService,
        organization_id: uuid.UUID,
    ) -> None:
        # The other order would make an assessment evaluate yesterday's
        # estate and report it as today's.
        await make_evidence(
            "host-1", {"firewall": {"enabled": False}}, collected_at=utcnow() - timedelta(days=2)
        )
        await make_evidence("host-1", {"firewall": {"enabled": True}})
        merged = await evidence_service.payload_for_targets(organization_id, ["host-1"])
        assert merged["host-1"]["firewall"]["enabled"] is True

    async def test_collecting_publishes_the_digest_not_the_payload(
        self, make_evidence: MakeControlFn, publisher: RecordingPublisher
    ) -> None:
        # Evidence can contain exactly the configuration detail an
        # organization is least willing to broadcast on a shared bus.
        stored = await make_evidence("host-1", {"secret": "hunter2"})
        assert "EvidenceCollected" in publisher.names
        published = publisher.events[-1].payload
        assert published["digest"] == stored.digest
        assert "secret" not in str(published)


class TestAssessments:
    async def _catalogue(
        self, make_framework: MakeControlFn, make_control: MakeControlFn
    ) -> tuple[Any, Any]:
        framework = await make_framework("cis")
        control = await make_control(framework.id, "1.1")
        return framework, control

    async def test_a_run_evaluates_and_records_every_verdict(
        self,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework, _control = await self._catalogue(make_framework, make_control)
        planned = await assessment_service.create(
            organization_id, name="Q3", framework_id=framework.id
        )
        finished = await assessment_service.run(
            organization_id,
            planned.id,
            targets=[
                Target("host-1", "server", payload={"firewall": {"enabled": True}}),
                Target("host-2", "server", payload={"firewall": {"enabled": False}}),
            ],
        )
        assert finished.controls_passed == 1
        assert finished.controls_failed == 1
        assert finished.score == 50.0

        results = await assessment_service.results_for(organization_id, planned.id)
        assert len(results) == 2

    async def test_a_target_with_no_payload_is_filled_from_stored_evidence(
        self,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        make_evidence: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # The property that makes a historical assessment reproducible:
        # it can be re-run from stored evidence with no collector present.
        framework, _control = await self._catalogue(make_framework, make_control)
        await make_evidence("host-1", {"firewall": {"enabled": True}})
        planned = await assessment_service.create(
            organization_id, name="From evidence", framework_id=framework.id
        )
        finished = await assessment_service.run(
            organization_id, planned.id, targets=[Target("host-1", "server")]
        )
        assert finished.controls_passed == 1

    async def test_a_target_with_no_evidence_anywhere_is_not_assessed(
        self,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework, _control = await self._catalogue(make_framework, make_control)
        planned = await assessment_service.create(
            organization_id, name="Blind", framework_id=framework.id
        )
        finished = await assessment_service.run(
            organization_id, planned.id, targets=[Target("host-x", "server")]
        )
        assert finished.controls_not_assessed == 1
        assert finished.controls_passed == 0, "an uninspected host is never certified"

    async def test_a_live_exception_excepts_a_failure_and_is_counted(
        self,
        assessment_service: AssessmentService,
        exception_service: ExceptionService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
        db_session: AsyncSession,
    ) -> None:
        framework, control = await self._catalogue(make_framework, make_control)
        waiver = await exception_service.request(
            organization_id,
            control_id=control.id,
            title="Legacy host",
            business_justification="Vendor appliance; firewall is upstream.",
            expires_at=soon(30),
        )
        await exception_service.approve(organization_id, waiver.id, approved_by="ciso")

        planned = await assessment_service.create(
            organization_id, name="Waived", framework_id=framework.id
        )
        finished = await assessment_service.run(
            organization_id,
            planned.id,
            targets=[Target("host-1", "server", payload={"firewall": {"enabled": False}})],
        )
        assert finished.controls_excepted == 1
        assert finished.controls_failed == 0

        await db_session.refresh(waiver)
        assert waiver.use_count == 1, "reliance on a waiver is counted every time"

    async def test_a_finished_run_cannot_be_run_again(
        self,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # Overwriting results an audit may already have been shown is
        # never the right action; a new assessment is.
        framework, _control = await self._catalogue(make_framework, make_control)
        planned = await assessment_service.create(
            organization_id, name="Once", framework_id=framework.id
        )
        await assessment_service.run(organization_id, planned.id, targets=[])
        with pytest.raises(ConflictError, match="cannot be run again"):
            await assessment_service.run(organization_id, planned.id, targets=[])

    async def test_a_run_publishes_started_and_completed(
        self,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
        publisher: RecordingPublisher,
    ) -> None:
        framework, _control = await self._catalogue(make_framework, make_control)
        planned = await assessment_service.create(
            organization_id, name="Events", framework_id=framework.id
        )
        await assessment_service.run(organization_id, planned.id, targets=[])
        assert "ComplianceAssessmentStarted" in publisher.names
        assert "ComplianceAssessmentCompleted" in publisher.names

    async def test_a_corrupt_control_is_skipped_not_fatal(
        self,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
        db_session: AsyncSession,
    ) -> None:
        # One corrupt row must not stop an organization being assessed.
        framework, _control = await self._catalogue(make_framework, make_control)
        broken = await make_control(framework.id, "9.9")
        broken.rule = {"checks": [{"path": "a", "operator": "telepathy"}]}
        await db_session.flush()

        planned = await assessment_service.create(
            organization_id, name="Partial catalogue", framework_id=framework.id
        )
        finished = await assessment_service.run(
            organization_id,
            planned.id,
            targets=[Target("host-1", "server", payload={"firewall": {"enabled": True}})],
        )
        assert finished.controls_total == 1, "the loadable control still ran"

    async def test_cancelling_a_finished_run_is_refused(
        self,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework, _control = await self._catalogue(make_framework, make_control)
        planned = await assessment_service.create(
            organization_id, name="Done", framework_id=framework.id
        )
        await assessment_service.run(organization_id, planned.id, targets=[])
        with pytest.raises(ConflictError):
            await assessment_service.cancel(organization_id, planned.id)

    async def test_a_stuck_run_is_reaped_so_the_next_one_can_start(
        self,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        organization_id: uuid.UUID,
        db_session: AsyncSession,
    ) -> None:
        # A RUNNING row left by a dead worker blocks the next scheduled
        # run for its framework, and the symptom is nothing happening --
        # the hardest kind of failure to notice.
        framework = await make_framework()
        planned = await assessment_service.create(
            organization_id, name="Abandoned", framework_id=framework.id
        )
        planned.status = AssessmentStatus.RUNNING
        planned.started_at = utcnow() - timedelta(hours=3)
        await db_session.flush()

        reaped = await assessment_service.reap_stuck(organization_id, older_than_minutes=60)
        assert len(reaped) == 1
        assert "presumed to have died" in (reaped[0].error or "")

    async def test_target_payloads_need_an_id(self) -> None:
        with pytest.raises(ValidationError, match="target_id"):
            target_from_payload({"target_type": "server"})

    async def test_a_target_payload_round_trips(self) -> None:
        target = target_from_payload(
            {"target_id": "h1", "target_type": "server", "payload": {"a": 1}}
        )
        assert target.target_id == "h1"
        assert target.payload == {"a": 1}


class TestFindings:
    async def _failure(self, control_id: str, target_id: str = "host-1") -> ControlResult:
        return ControlResult(
            control_id=control_id,
            framework_id=None,
            status=ResultStatus.FAIL,
            reason="firewall.enabled is_true but observed False",
            target_id=target_id,
            target_type="server",
            severity=ControlSeverity.HIGH,
        )

    async def test_the_same_problem_twice_updates_one_finding(
        self,
        finding_service: FindingService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # A daily assessment across a thousand hosts would otherwise
        # raise a third of a million findings a year for problems that
        # never changed.
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        first, is_new = await finding_service.raise_from_result(
            organization_id, await self._failure(str(control.id))
        )
        assert is_new is True

        second, is_new_again = await finding_service.raise_from_result(
            organization_id, await self._failure(str(control.id))
        )
        assert is_new_again is False
        assert second.id == first.id
        assert second.detection_count == 2

    async def test_the_age_of_a_re_detected_finding_is_preserved(
        self,
        finding_service: FindingService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # Age is the only number that makes an overdue problem visible.
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        long_ago = utcnow() - timedelta(days=200)
        first, _ = await finding_service.raise_from_result(
            organization_id, await self._failure(str(control.id)), now=long_ago
        )
        again, _ = await finding_service.raise_from_result(
            organization_id, await self._failure(str(control.id))
        )
        assert again.first_detected_at == first.first_detected_at
        assert again.last_detected_at > again.first_detected_at

    async def test_different_targets_are_different_findings(
        self,
        finding_service: FindingService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        first, _ = await finding_service.raise_from_result(
            organization_id, await self._failure(str(control.id), "host-1")
        )
        second, is_new = await finding_service.raise_from_result(
            organization_id, await self._failure(str(control.id), "host-2")
        )
        assert is_new is True
        assert second.id != first.id

    async def test_a_re_detected_closed_finding_reopens_rather_than_duplicating(
        self,
        finding_service: FindingService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # Two findings for one problem is how a queue stops being
        # trustworthy.
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        first, _ = await finding_service.raise_from_result(
            organization_id, await self._failure(str(control.id))
        )
        await finding_service.transition(
            organization_id, first.id, target=FindingStatus.CLOSED, note="Fixed."
        )

        reopened, is_new = await finding_service.raise_from_result(
            organization_id, await self._failure(str(control.id))
        )
        assert is_new is False
        assert reopened.id == first.id
        assert reopened.status == FindingStatus.OPEN
        reason = "a resolution date that did not hold must not survive the reopening"
        assert reopened.resolved_at is None, reason

    async def test_a_finding_cannot_be_marked_verified_by_hand(
        self,
        finding_service: FindingService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # VERIFIED means a re-assessment confirmed the control passes.
        # Setting it by hand would make the one status that means
        # *proven* mean *asserted*.
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        finding, _ = await finding_service.raise_from_result(
            organization_id, await self._failure(str(control.id))
        )
        with pytest.raises(ConflictError, match="re-assessment"):
            await finding_service.transition(
                organization_id, finding.id, target=FindingStatus.VERIFIED
            )

    async def test_assigning_a_closed_finding_is_refused(
        self,
        finding_service: FindingService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        finding, _ = await finding_service.raise_from_result(
            organization_id, await self._failure(str(control.id))
        )
        await finding_service.transition(organization_id, finding.id, target=FindingStatus.CLOSED)
        with pytest.raises(ConflictError):
            await finding_service.assign(organization_id, finding.id, assignee_id="alice")

    async def test_assigning_acknowledges_an_open_finding(
        self,
        finding_service: FindingService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        finding, _ = await finding_service.raise_from_result(
            organization_id, await self._failure(str(control.id))
        )
        assigned = await finding_service.assign(organization_id, finding.id, assignee_id="alice")
        assert assigned.status == FindingStatus.ACKNOWLEDGED
        assert assigned.assigned_at is not None

    async def test_a_finding_publishes_a_violation_once(
        self,
        finding_service: FindingService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
        publisher: RecordingPublisher,
    ) -> None:
        # A re-detection must not fire again, or a daily assessment
        # emits the same event 365 times a year per host.
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        await finding_service.raise_from_result(
            organization_id, await self._failure(str(control.id))
        )
        await finding_service.raise_from_result(
            organization_id, await self._failure(str(control.id))
        )
        assert publisher.names.count("ComplianceViolationDetected") == 1

    async def test_overdue_findings_are_findable(
        self,
        finding_service: FindingService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        await finding_service.raise_from_result(
            organization_id,
            await self._failure(str(control.id)),
            now=utcnow() - timedelta(days=90),
        )
        assert len(await finding_service.overdue(organization_id)) == 1

    async def test_the_summary_counts_open_by_severity(
        self,
        finding_service: FindingService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        await finding_service.raise_from_result(
            organization_id, await self._failure(str(control.id))
        )
        summary = await finding_service.summary(organization_id)
        assert summary["open_total"] == 1
        assert summary["by_severity"]["high"] == 1

    async def test_notifying_critical_failures_survives_a_dead_channel(
        self, finding_service: FindingService
    ) -> None:
        # The fixture registers no channel, so every send genuinely
        # fails. An assessment that walked five thousand hosts must not
        # lose its results to an unreachable SMTP server.
        sent = await finding_service.notify_critical(
            [await self._failure("c1")], notify_user_id="user-1"
        )
        assert sent == 1

    async def test_notifying_nobody_sends_nothing(self, finding_service: FindingService) -> None:
        assert await finding_service.notify_critical([], notify_user_id="u") == 0
        assert (
            await finding_service.notify_critical([await self._failure("c1")], notify_user_id=None)
            == 0
        )
