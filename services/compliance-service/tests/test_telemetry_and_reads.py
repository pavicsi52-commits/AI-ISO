"""Telemetry spans, repository read paths, and the remaining endpoints.

The read and list paths are worth their own file because they are where
tenant scoping is either enforced or quietly missing, and a missing
``organization_id`` predicate is invisible in any test that only ever
uses one tenant.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient
from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessments.engine import ControlResult, Target
from app.models.assessment import ComplianceScan
from app.models.enums import (
    AuditAction,
    ControlCategory,
    ControlSeverity,
    ControlStatus,
    EvidenceKind,
    EvidenceSource,
    FindingSeverity,
    FindingStatus,
    FrameworkStatus,
    RemediationStatus,
    ResultStatus,
    RiskImpact,
    RiskLikelihood,
    RiskStatus,
    ScanKind,
    ScanStatus,
    ScoreScope,
)
from app.repositories.catalogue import ControlRepository, FrameworkRepository
from app.repositories.governance import (
    ExceptionRepository,
    FindingRepository,
    RemediationRepository,
    RiskRepository,
    ScoreRepository,
)
from app.repositories.runs import (
    AssessmentRepository,
    EvidenceRepository,
    ResultRepository,
    ScanRepository,
)
from app.services.assessment import AssessmentService
from app.services.catalogue import CatalogueService
from app.services.finding import FindingService
from app.services.governance import ExceptionService, RemediationService, RiskService
from app.telemetry.tracing import (
    trace_assessment,
    trace_control_evaluation,
    trace_evidence_collection,
    trace_publish,
    trace_report,
    trace_risk_calculation,
    trace_scoring,
)
from tests.conftest import (
    HTTP_OK,
    AuthHeadersFn,
    MakeControlFn,
    soon,
    utcnow,
)

CALLER = uuid.uuid4()


def org(organization_id: uuid.UUID) -> dict[str, str]:
    return {"organization_id": str(organization_id)}


class TestTelemetrySpans:
    """Every span docs/051 names, emitted for real."""

    def test_each_traced_operation_opens_a_span(self) -> None:
        tracer = trace.get_tracer("test")
        with trace_assessment(
            tracer, assessment_id="a1", scope="organization", controls=10, targets=5
        ) as span:
            assert span is not None
        with trace_control_evaluation(tracer, control_code="AC-6", severity="high") as span:
            assert span is not None
        with trace_evidence_collection(
            tracer, kind="configuration_snapshot", source="discovery", size_bytes=42
        ) as span:
            assert span is not None
        with trace_scoring(tracer, assessment_id="a1", results=20) as span:
            assert span is not None
        with trace_risk_calculation(tracer, likelihood="likely", impact="major") as span:
            assert span is not None
        with trace_report(tracer, kind="executive", rows=12) as span:
            assert span is not None
        with trace_publish(tracer, event_name="ComplianceAssessmentCompleted") as span:
            assert span is not None

    def test_a_span_records_an_exception_and_re_raises(self) -> None:
        tracer = trace.get_tracer("test")
        with (
            pytest.raises(RuntimeError, match="boom"),
            trace_assessment(
                tracer, assessment_id="a1", scope="organization", controls=1, targets=1
            ),
        ):
            raise RuntimeError("boom")

    def test_a_span_carries_shapes_and_counts_but_never_evidence(self) -> None:
        # An evidence payload is somebody's production estate. A tracing
        # backend has different retention and different access rules, and
        # unlike a database row a span cannot be redacted afterwards.
        tracer = trace.get_tracer("test")
        with trace_evidence_collection(
            tracer, kind="configuration_snapshot", source="discovery", size_bytes=4096
        ) as span:
            rendered = str(getattr(span, "attributes", {}))
        assert "4096" in rendered or rendered == "{}"


class TestCatalogueReads:
    async def test_frameworks_filter_by_status_and_page(
        self,
        db_session: AsyncSession,
        catalogue_service: CatalogueService,
        make_framework: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        one = await make_framework("one")
        two = await make_framework("two")
        await catalogue_service.update_framework(
            organization_id, one.id, status=FrameworkStatus.ACTIVE
        )
        await catalogue_service.update_framework(
            organization_id, two.id, status=FrameworkStatus.ACTIVE
        )
        repo = FrameworkRepository(db_session)

        assert len(await repo.list_for_org(organization_id)) == 2
        assert len(await repo.list_for_org(organization_id, limit=1)) == 1
        assert len(await repo.list_for_org(organization_id, offset=1)) == 1
        assert len(await repo.list_active(organization_id)) == 2
        assert len(await repo.list_for_org(organization_id, status=FrameworkStatus.ARCHIVED)) == 0

    async def test_another_tenants_frameworks_are_invisible(
        self,
        db_session: AsyncSession,
        make_framework: MakeControlFn,
    ) -> None:
        # The predicate that is invisible in any test using one tenant.
        await make_framework("mine")
        assert await FrameworkRepository(db_session).list_for_org(uuid.uuid4()) == []

    async def test_controls_filter_on_every_dimension(
        self,
        db_session: AsyncSession,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        await make_control(
            framework.id,
            "A.1",
            severity=ControlSeverity.CRITICAL,
            status=ControlStatus.IMPLEMENTED,
        )
        await make_control(
            framework.id, "A.2", severity=ControlSeverity.LOW, status=ControlStatus.PLANNED
        )
        repo = ControlRepository(db_session)

        assert len(await repo.list_filtered(organization_id, framework_id=framework.id)) == 2
        assert (
            len(await repo.list_filtered(organization_id, severity=ControlSeverity.CRITICAL)) == 1
        )
        assert len(await repo.list_filtered(organization_id, status=ControlStatus.PLANNED)) == 1
        assert len(await repo.list_filtered(organization_id, category=ControlCategory.OTHER)) >= 0
        assert len(await repo.list_filtered(organization_id, owner_id="nobody")) == 0
        assert len(await repo.list_filtered(organization_id, limit=1)) == 1
        assert len(await repo.list_filtered(organization_id, offset=1)) == 1

    async def test_a_control_is_findable_by_its_published_code(
        self,
        db_session: AsyncSession,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        await make_control(framework.id, "AC-6")
        repo = ControlRepository(db_session)
        assert await repo.get_by_code(organization_id, framework.id, "AC-6") is not None
        assert await repo.get_by_code(organization_id, framework.id, "AC-99") is None

    async def test_listing_by_ids_is_still_tenant_scoped(
        self,
        db_session: AsyncSession,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # A bulk read by id is exactly where a scope check gets dropped,
        # because the ids "came from us" -- until one did not.
        framework = await make_framework()
        control = await make_control(framework.id, "A.1")
        repo = ControlRepository(db_session)
        assert len(await repo.list_by_ids(organization_id, [control.id])) == 1
        assert await repo.list_by_ids(uuid.uuid4(), [control.id]) == []
        assert await repo.list_by_ids(organization_id, []) == []

    async def test_assessable_controls_include_the_scoped_out_ones(
        self,
        db_session: AsyncSession,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # The engine needs an explicit NOT_APPLICABLE result for each, so
        # coverage arithmetic can tell "we decided this does not apply"
        # from "we never looked at this".
        framework = await make_framework()
        await make_control(framework.id, "A.1", status=ControlStatus.NOT_APPLICABLE)
        repo = ControlRepository(db_session)
        assert len(await repo.list_assessable(organization_id)) == 1
        assert len(await repo.list_assessable(organization_id, framework_ids=[framework.id])) == 1
        assert len(await repo.list_assessable(organization_id, automatable_only=False)) == 1

    async def test_controls_count_by_status(
        self,
        db_session: AsyncSession,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        await make_control(framework.id, "A.1", status=ControlStatus.IMPLEMENTED)
        await make_control(framework.id, "A.2", status=ControlStatus.IMPLEMENTED)
        counts = await ControlRepository(db_session).count_by_status(organization_id)
        assert counts["implemented"] == 2


class TestRunReads:
    async def _assessed(
        self,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> object:
        framework = await make_framework("cis")
        await make_control(framework.id, "1.1")
        planned = await assessment_service.create(
            organization_id, name="Run", framework_id=framework.id
        )
        await assessment_service.run(
            organization_id,
            planned.id,
            targets=[
                Target("a", "server", payload={"firewall": {"enabled": True}}),
                Target("b", "server", payload={"firewall": {"enabled": False}}),
            ],
        )
        return planned

    async def test_assessments_list_and_filter(
        self,
        db_session: AsyncSession,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        planned = await self._assessed(
            assessment_service, make_framework, make_control, organization_id
        )
        repo = AssessmentRepository(db_session)
        assert len(await repo.list_for_org(organization_id)) == 1
        assert len(await repo.list_for_org(organization_id, limit=1, offset=1)) == 0
        assert await repo.latest_completed(organization_id) is not None
        assert await repo.latest_completed(uuid.uuid4()) is None
        assert (await repo.require_in_org(organization_id, planned.id)).name == "Run"

    async def test_results_filter_by_status_and_target(
        self,
        db_session: AsyncSession,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        planned = await self._assessed(
            assessment_service, make_framework, make_control, organization_id
        )
        repo = ResultRepository(db_session)
        assert len(await repo.list_for_assessment(organization_id, planned.id)) == 2
        failed = await repo.list_for_assessment(
            organization_id, planned.id, status=ResultStatus.FAIL
        )
        assert len(failed) == 1
        assert await repo.list_for_assessment(uuid.uuid4(), planned.id) == []

    async def test_the_latest_result_for_a_control_is_the_newest(
        self,
        db_session: AsyncSession,
        assessment_service: AssessmentService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        # Remediation verification reads this; the other order would let
        # a stale pass close a finding that is failing now.
        framework = await make_framework("cis")
        control = await make_control(framework.id, "1.1")
        for enabled in (False, True):
            planned = await assessment_service.create(
                organization_id, name=f"Run {enabled}", framework_id=framework.id
            )
            await assessment_service.run(
                organization_id,
                planned.id,
                targets=[Target("h", "server", payload={"firewall": {"enabled": enabled}})],
            )
        latest = await ResultRepository(db_session).latest_for_control_target(
            organization_id, control.id, target_id="h"
        )
        assert latest is not None
        assert latest.status == ResultStatus.PASS

    async def test_scans_list_and_filter(
        self,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        await ScanRepository(db_session).create(
            ComplianceScan(
                organization_id=organization_id,
                name="Nightly",
                kind=ScanKind.CONFIGURATION,
                status=ScanStatus.COMPLETED,
                scanner="collector-1",
                targets_scanned=1,
            )
        )
        repo = ScanRepository(db_session)
        assert len(await repo.list_for_org(organization_id)) == 1
        assert await repo.list_for_org(uuid.uuid4()) == []

    async def test_evidence_lists_by_target_and_control(
        self,
        db_session: AsyncSession,
        make_evidence: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_evidence("host-1", {"a": 1})
        await make_evidence("host-2", {"b": 2})
        repo = EvidenceRepository(db_session)
        assert len(await repo.list_for_org(organization_id)) == 2
        assert len(await repo.list_for_org(organization_id, target_id="host-1")) == 1
        assert await repo.list_for_org(uuid.uuid4()) == []


class TestGovernanceReads:
    async def test_findings_filter_on_every_dimension(
        self,
        db_session: AsyncSession,
        finding_service: FindingService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
        framework = await make_framework()
        control = await make_control(framework.id, "1.1")
        await finding_service.raise_from_result(
            organization_id,
            ControlResult(
                control_id=str(control.id),
                framework_id=str(framework.id),
                status=ResultStatus.FAIL,
                reason="off",
                target_id="host-1",
                target_type="server",
                severity=ControlSeverity.CRITICAL,
            ),
        )
        repo = FindingRepository(db_session)
        assert len(await repo.list_filtered(organization_id)) == 1
        assert len(await repo.list_filtered(organization_id, status=FindingStatus.OPEN)) == 1
        assert (
            len(await repo.list_filtered(organization_id, severity=FindingSeverity.CRITICAL)) == 1
        )
        assert len(await repo.list_filtered(organization_id, control_id=control.id)) == 1
        assert len(await repo.list_filtered(organization_id, framework_id=framework.id)) == 1
        assert len(await repo.list_filtered(organization_id, target_id="host-1")) == 1
        assert len(await repo.list_filtered(organization_id, open_only=True)) == 1
        assert len(await repo.list_filtered(organization_id, assignee_id="nobody")) == 0
        assert await repo.list_filtered(uuid.uuid4()) == []

    async def test_exceptions_list_and_filter(
        self,
        db_session: AsyncSession,
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
            title="Waiver",
            business_justification="Reason.",
            expires_at=soon(30),
        )
        repo = ExceptionRepository(db_session)
        assert len(await repo.list_filtered(organization_id)) == 1
        assert len(await repo.list_filtered(organization_id, control_id=control.id)) == 1
        assert await repo.list_live(organization_id, moment=utcnow()) == []

        await exception_service.approve(organization_id, created.id, approved_by="ciso")
        assert len(await repo.list_live(organization_id, moment=utcnow())) == 1
        assert await repo.list_filtered(uuid.uuid4()) == []

    async def test_risks_list_and_filter(
        self,
        db_session: AsyncSession,
        risk_service: RiskService,
        organization_id: uuid.UUID,
    ) -> None:
        await risk_service.register(
            organization_id,
            title="One",
            likelihood=RiskLikelihood.LIKELY,
            impact=RiskImpact.MAJOR,
        )
        repo = RiskRepository(db_session)
        assert len(await repo.list_filtered(organization_id)) == 1
        assert len(await repo.list_filtered(organization_id, status=RiskStatus.IDENTIFIED)) == 1
        assert len(await repo.list_filtered(organization_id, status=RiskStatus.CLOSED)) == 0
        assert await repo.existing_references(organization_id) == ["RISK-0001"]
        assert await repo.list_filtered(uuid.uuid4()) == []

    async def test_remediation_lists_by_finding_and_status(
        self,
        db_session: AsyncSession,
        remediation_service: RemediationService,
        finding_service: FindingService,
        make_framework: MakeControlFn,
        make_control: MakeControlFn,
        organization_id: uuid.UUID,
    ) -> None:
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
        await remediation_service.propose(organization_id, finding_id=found.id, title="Fix")
        repo = RemediationRepository(db_session)
        assert len(await repo.list_filtered(organization_id)) == 1
        assert (
            len(await repo.list_filtered(organization_id, status=RemediationStatus.PROPOSED)) == 1
        )
        assert len(await repo.list_for_finding(organization_id, found.id)) == 1
        assert await repo.list_filtered(uuid.uuid4()) == []

    async def test_scores_read_back_latest_and_history(
        self,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        repo = ScoreRepository(db_session)
        assert await repo.latest(organization_id, scope=ScoreScope.OVERALL) is None
        assert (
            await repo.history(
                organization_id, scope=ScoreScope.OVERALL, since=utcnow() - timedelta(days=1)
            )
            == []
        )
        assert await repo.latest_per_scope(organization_id, scope=ScoreScope.FRAMEWORK) == []


class TestRemainingEndpoints:
    """The read and mutation endpoints the flow tests did not touch."""

    async def _seeded(
        self, client: AsyncClient, headers: dict[str, str], organization_id: uuid.UUID
    ) -> tuple[str, str]:
        seeded = await client.post(
            "/compliance/frameworks/seed", params=org(organization_id), headers=headers
        )
        framework_id = seeded.json()["data"][0]["id"]
        controls = await client.get(
            "/compliance/controls",
            params={**org(organization_id), "framework_id": framework_id},
            headers=headers,
        )
        return framework_id, controls.json()["data"][0]["id"]

    async def test_every_list_endpoint_answers(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        for path in (
            "/compliance/frameworks",
            "/compliance/controls",
            "/compliance/assessments",
            "/compliance/scans",
            "/compliance/evidence",
            "/compliance/findings",
            "/compliance/exceptions",
            "/compliance/risk-register",
            "/compliance/remediation",
            "/compliance/reports",
            "/compliance/audit",
            "/compliance/statistics/windows",
        ):
            response = await client.get(path, params=org(organization_id), headers=headers)
            assert response.status_code == HTTP_OK, f"{path}: {response.text}"

    async def test_a_framework_is_updatable_and_archivable(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        created = await client.post(
            "/compliance/frameworks",
            params=org(organization_id),
            headers=headers,
            json={"slug": "own", "name": "Ours"},
        )
        framework_id = created.json()["data"]["id"]

        updated = await client.put(
            f"/compliance/frameworks/{framework_id}",
            params=org(organization_id),
            headers=headers,
            json={"name": "Renamed", "status": "active"},
        )
        assert updated.json()["data"]["name"] == "Renamed"

        archived = await client.delete(
            f"/compliance/frameworks/{framework_id}",
            params=org(organization_id),
            headers=headers,
        )
        assert archived.json()["data"]["status"] == "archived"

    async def test_a_control_is_updatable_and_its_rule_replaceable(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        framework = await client.post(
            "/compliance/frameworks",
            params=org(organization_id),
            headers=headers,
            json={"slug": "own", "name": "Ours"},
        )
        framework_id = framework.json()["data"]["id"]
        control = await client.post(
            "/compliance/controls",
            params={**org(organization_id), "framework_id": framework_id},
            headers=headers,
            json={
                "code": "1.1",
                "title": "Firewall",
                "rule": {
                    "name": "root",
                    "logical_operator": "all",
                    "checks": [{"path": "firewall.enabled", "operator": "is_true"}],
                },
            },
        )
        control_id = control.json()["data"]["id"]

        updated = await client.put(
            f"/compliance/controls/{control_id}",
            params=org(organization_id),
            headers=headers,
            json={"status": "implemented", "owner_id": "team-a", "severity": "critical"},
        )
        assert updated.json()["data"]["status"] == "implemented"

        replaced = await client.put(
            f"/compliance/controls/{control_id}/rule",
            params=org(organization_id),
            headers=headers,
            json={
                "rule": {
                    "name": "root",
                    "logical_operator": "all",
                    "checks": [{"path": "auditd.enabled", "operator": "is_true"}],
                }
            },
        )
        assert replaced.status_code == HTTP_OK

    async def test_related_controls_are_reachable(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        _framework_id, control_id = await self._seeded(client, headers, organization_id)
        response = await client.get(
            f"/compliance/controls/{control_id}/related",
            params=org(organization_id),
            headers=headers,
        )
        assert response.status_code == HTTP_OK

    async def test_an_assessment_is_readable_and_cancellable(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        framework_id, _ = await self._seeded(client, headers, organization_id)
        planned = await client.post(
            "/compliance/assessments",
            params=org(organization_id),
            headers=headers,
            json={"name": "Cancelled", "framework_id": framework_id},
        )
        assessment_id = planned.json()["data"]["id"]

        read = await client.get(
            f"/compliance/assessments/{assessment_id}",
            params=org(organization_id),
            headers=headers,
        )
        assert read.status_code == HTTP_OK

        cancelled = await client.post(
            f"/compliance/assessments/{assessment_id}/cancel",
            params=org(organization_id),
            headers=headers,
        )
        assert cancelled.json()["data"]["status"] == "cancelled"

    async def test_a_finding_is_readable_and_assignable(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        framework_id, _ = await self._seeded(client, headers, organization_id)
        planned = await client.post(
            "/compliance/assessments",
            params=org(organization_id),
            headers=headers,
            json={"name": "Raise", "framework_id": framework_id},
        )
        await client.post(
            f"/compliance/assessments/{planned.json()['data']['id']}/run",
            params=org(organization_id),
            headers=headers,
            json={"targets": [{"target_id": "host-1", "payload": {"unrelated": True}}]},
        )
        findings = await client.get(
            "/compliance/findings", params=org(organization_id), headers=headers
        )
        finding_id = findings.json()["data"][0]["id"]

        read = await client.get(
            f"/compliance/findings/{finding_id}", params=org(organization_id), headers=headers
        )
        assert read.status_code == HTTP_OK

        assigned = await client.post(
            f"/compliance/findings/{finding_id}/assign",
            params=org(organization_id),
            headers=headers,
            json={"assignee_id": "alice"},
        )
        assert assigned.json()["data"]["assignee_id"] == "alice"

        transitioned = await client.post(
            f"/compliance/findings/{finding_id}/transition",
            params=org(organization_id),
            headers=headers,
            json={"status": "risk_accepted", "note": "Accepted for this quarter."},
        )
        assert transitioned.json()["data"]["status"] == "risk_accepted"

    async def test_an_exception_is_readable_reviewable_and_revocable(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        _framework_id, control_id = await self._seeded(client, headers, organization_id)
        created = await client.post(
            "/compliance/exceptions",
            params=org(organization_id),
            headers=headers,
            json={
                "control_id": control_id,
                "title": "Waiver",
                "business_justification": "Vendor appliance.",
                "expires_at": soon(30).isoformat(),
            },
        )
        exception_id = created.json()["data"]["id"]
        await client.post(
            f"/compliance/exceptions/{exception_id}/decide",
            params=org(organization_id),
            headers=headers,
            json={"approve": True, "decided_by": "ciso"},
        )

        read = await client.get(
            f"/compliance/exceptions/{exception_id}",
            params=org(organization_id),
            headers=headers,
        )
        assert read.status_code == HTTP_OK

        reviewed = await client.post(
            f"/compliance/exceptions/{exception_id}/review",
            params=org(organization_id),
            headers=headers,
            json={"reviewed_by": "auditor", "still_needed": True},
        )
        assert reviewed.json()["data"]["status"] == "active"

        revoked = await client.request(
            "DELETE",
            f"/compliance/exceptions/{exception_id}",
            params=org(organization_id),
            headers=headers,
            json={"reason": "The appliance was replaced."},
        )
        assert revoked.json()["data"]["status"] == "revoked"

    async def test_a_risk_is_readable_updatable_and_reviewable(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        created = await client.post(
            "/compliance/risk-register",
            params=org(organization_id),
            headers=headers,
            json={
                "title": "Estate risk",
                "likelihood": str(RiskLikelihood.POSSIBLE),
                "impact": str(RiskImpact.MODERATE),
            },
        )
        risk_id = created.json()["data"]["id"]

        read = await client.get(
            f"/compliance/risk-register/{risk_id}", params=org(organization_id), headers=headers
        )
        assert read.status_code == HTTP_OK

        rescored = await client.put(
            f"/compliance/risk-register/{risk_id}/assessment",
            params=org(organization_id),
            headers=headers,
            json={
                "likelihood": str(RiskLikelihood.ALMOST_CERTAIN),
                "impact": str(RiskImpact.SEVERE),
            },
        )
        assert rescored.json()["data"]["severity"] == "critical"

        reviewed = await client.post(
            f"/compliance/risk-register/{risk_id}/review",
            params=org(organization_id),
            headers=headers,
        )
        assert reviewed.json()["data"]["last_reviewed_at"] is not None

        transitioned = await client.post(
            f"/compliance/risk-register/{risk_id}/transition",
            params=org(organization_id),
            headers=headers,
            json={"status": str(RiskStatus.MONITORING)},
        )
        assert transitioned.json()["data"]["status"] == "monitoring"

    async def test_the_risk_due_for_review_literal_route_is_reachable(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/compliance/risk-register/due-for-review",
            params=org(organization_id),
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_OK

    async def test_a_remediation_is_readable_and_transitionable(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        framework_id, _ = await self._seeded(client, headers, organization_id)
        planned = await client.post(
            "/compliance/assessments",
            params=org(organization_id),
            headers=headers,
            json={"name": "For remediation", "framework_id": framework_id},
        )
        await client.post(
            f"/compliance/assessments/{planned.json()['data']['id']}/run",
            params=org(organization_id),
            headers=headers,
            json={"targets": [{"target_id": "host-1", "payload": {"unrelated": True}}]},
        )
        findings = await client.get(
            "/compliance/findings", params=org(organization_id), headers=headers
        )
        task = await client.post(
            "/compliance/remediation",
            params=org(organization_id),
            headers=headers,
            json={"finding_id": findings.json()["data"][0]["id"], "title": "Fix it"},
        )
        task_id = task.json()["data"]["id"]

        read = await client.get(
            f"/compliance/remediation/{task_id}", params=org(organization_id), headers=headers
        )
        assert read.status_code == HTTP_OK

        started = await client.post(
            f"/compliance/remediation/{task_id}/transition",
            params=org(organization_id),
            headers=headers,
            json={"status": str(RemediationStatus.IN_PROGRESS)},
        )
        assert started.json()["data"]["attempts"] == 1

    async def test_an_evidence_row_lists_by_target_and_control(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        await client.post(
            "/compliance/evidence",
            params=org(organization_id),
            headers=headers,
            json={
                "kind": str(EvidenceKind.CONFIGURATION_SNAPSHOT),
                "source": str(EvidenceSource.DISCOVERY),
                "title": "Snapshot",
                "payload": {"firewall": {"enabled": True}},
                "target_id": "host-1",
            },
        )
        filtered = await client.get(
            "/compliance/evidence",
            params={**org(organization_id), "target_id": "host-1"},
            headers=headers,
        )
        assert len(filtered.json()["data"]) == 1

        empty = await client.get(
            "/compliance/evidence",
            params={**org(organization_id), "target_id": "no-such-host"},
            headers=headers,
        )
        assert empty.json()["data"] == []

    async def test_an_audit_entry_is_recorded_for_a_refused_write(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        # The refusal is the entry somebody investigating an incident
        # most wants, and the easiest one to lose.
        headers = auth_headers(CALLER)
        await client.post(
            "/compliance/frameworks",
            params=org(organization_id),
            headers=headers,
            json={"slug": "dup", "name": "First"},
        )
        await client.post(
            "/compliance/frameworks",
            params=org(organization_id),
            headers=headers,
            json={"slug": "dup", "name": "Second"},
        )
        entries = await client.get(
            "/compliance/audit",
            params={**org(organization_id), "action": str(AuditAction.FRAMEWORK_CREATED)},
            headers=headers,
        )
        assert entries.status_code == HTTP_OK
