"""HTTP contract tests against the real app.

The full lifespan runs: PostgreSQL, Redis, RabbitMQ, notifications, and
key loading are all real. Only the request session is overridden.

See the conftest docstring for the one behaviour this file cannot check
-- anything whose correctness depends on transaction lifetime, because
the SAVEPOINT override is exactly what changes that.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from app.models.enums import (
    EvidenceKind,
    EvidenceSource,
    FindingStatus,
    ReportKind,
    RiskImpact,
    RiskLikelihood,
    RiskStatus,
)
from tests.conftest import (
    HTTP_BAD_REQUEST,
    HTTP_CONFLICT,
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
    AuthHeadersFn,
    soon,
)

CALLER = uuid.uuid4()


def org(organization_id: uuid.UUID) -> dict[str, str]:
    return {"organization_id": str(organization_id)}


def rule_payload(path: str = "firewall.enabled") -> dict[str, Any]:
    return {
        "rule": {
            "name": "root",
            "logical_operator": "all",
            "checks": [{"path": path, "operator": "is_true"}],
        }
    }


class TestHealth:
    async def test_health_liveness_and_metrics_answer(self, client: AsyncClient) -> None:
        assert (await client.get("/health")).status_code == HTTP_OK
        assert (await client.get("/liveness")).status_code == HTTP_OK
        assert (await client.get("/metrics")).status_code == HTTP_OK

    async def test_readiness_reports_database_and_cache(self, client: AsyncClient) -> None:
        response = await client.get("/readiness")
        assert response.status_code == HTTP_OK
        names = {one["name"] for one in response.json()["data"]["checks"]}
        assert {"database", "cache"} <= names

    async def test_the_openapi_document_describes_the_surface(self, client: AsyncClient) -> None:
        spec = (await client.get("/openapi.json")).json()
        operations = sum(
            len([m for m in ops if m in ("get", "post", "put", "patch", "delete")])
            for ops in spec["paths"].values()
        )
        assert operations >= 60


class TestAuthentication:
    async def test_an_unauthenticated_write_is_refused(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/compliance/frameworks",
            params=org(organization_id),
            json={"slug": "iso", "name": "ISO"},
        )
        assert response.status_code == HTTP_UNAUTHORIZED

    async def test_a_garbage_token_is_refused(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/compliance/frameworks",
            params=org(organization_id),
            headers={"Authorization": "Bearer not-a-token"},
            json={"slug": "iso", "name": "ISO"},
        )
        assert response.status_code == HTTP_UNAUTHORIZED


class TestCatalogueApi:
    async def _framework(
        self, client: AsyncClient, headers: dict[str, str], organization_id: uuid.UUID
    ) -> str:
        created = await client.post(
            "/compliance/frameworks",
            params=org(organization_id),
            headers=headers,
            json={"slug": "cis", "name": "CIS", "code": "cis_benchmarks", "kind": "security"},
        )
        assert created.status_code == HTTP_CREATED, created.text
        return str(created.json()["data"]["id"])

    async def _control(
        self,
        client: AsyncClient,
        headers: dict[str, str],
        organization_id: uuid.UUID,
        framework_id: str,
        code: str = "1.1",
    ) -> str:
        created = await client.post(
            "/compliance/controls",
            params={**org(organization_id), "framework_id": framework_id},
            headers=headers,
            json={
                "code": code,
                "title": f"Control {code}",
                "severity": "high",
                "status": "implemented",
                **rule_payload(),
            },
        )
        assert created.status_code == HTTP_CREATED, created.text
        return str(created.json()["data"]["id"])

    async def test_a_framework_and_control_round_trip(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        framework_id = await self._framework(client, headers, organization_id)
        control_id = await self._control(client, headers, organization_id, framework_id)

        read = await client.get(
            f"/compliance/controls/{control_id}", params=org(organization_id), headers=headers
        )
        assert read.status_code == HTTP_OK
        assert read.json()["data"]["is_automatable"] is True

    async def test_a_duplicate_slug_is_a_409(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        await self._framework(client, headers, organization_id)
        second = await client.post(
            "/compliance/frameworks",
            params=org(organization_id),
            headers=headers,
            json={"slug": "cis", "name": "CIS again"},
        )
        assert second.status_code == HTTP_CONFLICT

    async def test_an_invalid_slug_is_a_400(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        # The platform maps RequestValidationError to 400, not 422.
        response = await client.post(
            "/compliance/frameworks",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"slug": "Not A Slug!", "name": "Bad"},
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_an_unknown_framework_is_a_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            f"/compliance/frameworks/{uuid.uuid4()}",
            params=org(organization_id),
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_NOT_FOUND

    async def test_another_organizations_framework_is_a_404_not_a_403(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        # Telling a caller it exists but belongs to somebody else
        # confirms the id, which is the one thing they did not know.
        headers = auth_headers(CALLER)
        framework_id = await self._framework(client, headers, organization_id)
        response = await client.get(
            f"/compliance/frameworks/{framework_id}",
            params={"organization_id": str(uuid.uuid4())},
            headers=headers,
        )
        assert response.status_code == HTTP_NOT_FOUND

    async def test_seeding_is_idempotent_and_answers_200(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        # 200 rather than 201 because the common case is "nothing was
        # missing", and a 201 for an empty list would be a lie.
        headers = auth_headers(CALLER)
        first = await client.post(
            "/compliance/frameworks/seed", params=org(organization_id), headers=headers
        )
        assert first.status_code == HTTP_OK
        assert len(first.json()["data"]) == 5

        second = await client.post(
            "/compliance/frameworks/seed", params=org(organization_id), headers=headers
        )
        assert second.json()["data"] == []

    async def test_the_seed_literal_route_is_not_shadowed_by_the_id_route(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        # /frameworks/seed declared after /frameworks/{framework_id}
        # would be parsed as a framework whose id is the word "seed".
        response = await client.post(
            "/compliance/frameworks/seed",
            params=org(organization_id),
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_OK

    async def test_mapping_a_control_to_itself_is_a_400(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        framework_id = await self._framework(client, headers, organization_id)
        control_id = await self._control(client, headers, organization_id, framework_id)
        response = await client.post(
            "/compliance/controls/map",
            params=org(organization_id),
            headers=headers,
            json={"source_control_id": control_id, "target_control_id": control_id},
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_implementation_summary_is_reachable(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/compliance/controls/summary/implementation",
            params=org(organization_id),
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_OK

    async def test_a_builtin_framework_cannot_be_reworded_over_http(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        seeded = await client.post(
            "/compliance/frameworks/seed", params=org(organization_id), headers=headers
        )
        framework_id = seeded.json()["data"][0]["id"]
        response = await client.put(
            f"/compliance/frameworks/{framework_id}",
            params=org(organization_id),
            headers=headers,
            json={"name": "Our own CIS"},
        )
        assert response.status_code == HTTP_CONFLICT


class TestAssessmentApi:
    async def _prepared(
        self, client: AsyncClient, headers: dict[str, str], organization_id: uuid.UUID
    ) -> tuple[str, str]:
        framework = await client.post(
            "/compliance/frameworks",
            params=org(organization_id),
            headers=headers,
            json={"slug": "cis", "name": "CIS"},
        )
        framework_id = str(framework.json()["data"]["id"])
        control = await client.post(
            "/compliance/controls",
            params={**org(organization_id), "framework_id": framework_id},
            headers=headers,
            json={
                "code": "1.1",
                "title": "Firewall enabled",
                "severity": "critical",
                "status": "implemented",
                **rule_payload(),
            },
        )
        return framework_id, str(control.json()["data"]["id"])

    async def test_the_whole_assessment_flow(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        framework_id, _control_id = await self._prepared(client, headers, organization_id)

        planned = await client.post(
            "/compliance/assessments",
            params=org(organization_id),
            headers=headers,
            json={"name": "Q3", "framework_id": framework_id},
        )
        assert planned.status_code == HTTP_CREATED
        assessment_id = str(planned.json()["data"]["id"])

        run = await client.post(
            f"/compliance/assessments/{assessment_id}/run",
            params=org(organization_id),
            headers=headers,
            json={
                "targets": [
                    {
                        "target_id": "host-1",
                        "target_type": "server",
                        "payload": {"firewall": {"enabled": False}},
                    }
                ]
            },
        )
        assert run.status_code == HTTP_OK, run.text
        data = run.json()["data"]
        assert data["controls_failed"] == 1
        assert data["findings_raised"] == 1

        findings = await client.get(
            "/compliance/findings", params=org(organization_id), headers=headers
        )
        assert len(findings.json()["data"]) == 1

        score = await client.get("/compliance/scores", params=org(organization_id), headers=headers)
        assert score.json()["data"]["score"] == 0.0
        assert "coverage" in score.json()["data"]["breakdown"]

    async def test_running_twice_is_a_409(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        framework_id, _ = await self._prepared(client, headers, organization_id)
        planned = await client.post(
            "/compliance/assessments",
            params=org(organization_id),
            headers=headers,
            json={"name": "Once", "framework_id": framework_id},
        )
        assessment_id = str(planned.json()["data"]["id"])
        await client.post(
            f"/compliance/assessments/{assessment_id}/run",
            params=org(organization_id),
            headers=headers,
            json={"targets": []},
        )
        again = await client.post(
            f"/compliance/assessments/{assessment_id}/run",
            params=org(organization_id),
            headers=headers,
            json={"targets": []},
        )
        assert again.status_code == HTTP_CONFLICT

    async def test_a_rehearsal_run_raises_no_findings(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        # For somebody checking what a new control would flag before
        # committing to owning the queue it creates.
        headers = auth_headers(CALLER)
        framework_id, _ = await self._prepared(client, headers, organization_id)
        planned = await client.post(
            "/compliance/assessments",
            params=org(organization_id),
            headers=headers,
            json={"name": "Rehearsal", "framework_id": framework_id},
        )
        assessment_id = str(planned.json()["data"]["id"])
        await client.post(
            f"/compliance/assessments/{assessment_id}/run",
            params=org(organization_id),
            headers=headers,
            json={
                "raise_findings": False,
                "targets": [
                    {
                        "target_id": "host-1",
                        "payload": {"firewall": {"enabled": False}},
                    }
                ],
            },
        )
        findings = await client.get(
            "/compliance/findings", params=org(organization_id), headers=headers
        )
        assert findings.json()["data"] == []

    async def test_results_are_listable_and_filterable(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        framework_id, _ = await self._prepared(client, headers, organization_id)
        planned = await client.post(
            "/compliance/assessments",
            params=org(organization_id),
            headers=headers,
            json={"name": "Results", "framework_id": framework_id},
        )
        assessment_id = str(planned.json()["data"]["id"])
        await client.post(
            f"/compliance/assessments/{assessment_id}/run",
            params=org(organization_id),
            headers=headers,
            json={
                "targets": [
                    {"target_id": "a", "payload": {"firewall": {"enabled": True}}},
                    {"target_id": "b", "payload": {"firewall": {"enabled": False}}},
                ]
            },
        )
        all_results = await client.get(
            f"/compliance/assessments/{assessment_id}/results",
            params=org(organization_id),
            headers=headers,
        )
        assert len(all_results.json()["data"]) == 2

        failed = await client.get(
            f"/compliance/assessments/{assessment_id}/results",
            params={**org(organization_id), "status": "fail"},
            headers=headers,
        )
        assert len(failed.json()["data"]) == 1

    async def test_a_scan_records_evidence_that_a_later_run_can_use(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        framework_id, _ = await self._prepared(client, headers, organization_id)
        scan = await client.post(
            "/compliance/scan",
            params=org(organization_id),
            headers=headers,
            json={
                "name": "Nightly",
                "scanner": "collector-1",
                "targets": [{"target_id": "host-1", "payload": {"firewall": {"enabled": True}}}],
            },
        )
        assert scan.status_code == HTTP_CREATED
        assert scan.json()["data"]["targets_scanned"] == 1

        planned = await client.post(
            "/compliance/assessments",
            params=org(organization_id),
            headers=headers,
            json={"name": "From scan", "framework_id": framework_id},
        )
        run = await client.post(
            f"/compliance/assessments/{planned.json()['data']['id']}/run",
            params=org(organization_id),
            headers=headers,
            json={"targets": [{"target_id": "host-1"}]},
        )
        assert run.json()["data"]["controls_passed"] == 1


class TestEvidenceApi:
    async def test_evidence_is_recorded_and_verified_on_read(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        created = await client.post(
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
        assert created.status_code == HTTP_CREATED
        evidence_id = created.json()["data"]["id"]

        read = await client.get(
            f"/compliance/evidence/{evidence_id}", params=org(organization_id), headers=headers
        )
        assert read.status_code == HTTP_OK
        assert "integrity verified" in read.json()["message"]

    async def test_empty_evidence_is_a_400(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/compliance/evidence",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={
                "kind": str(EvidenceKind.REPORT),
                "source": str(EvidenceSource.MANUAL_UPLOAD),
                "title": "Nothing",
                "payload": {},
            },
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_supersession_keeps_both_rows(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        created = await client.post(
            "/compliance/evidence",
            params=org(organization_id),
            headers=headers,
            json={
                "kind": str(EvidenceKind.CONFIGURATION_SNAPSHOT),
                "source": str(EvidenceSource.DISCOVERY),
                "title": "First",
                "payload": {"v": 1},
                "target_id": "host-1",
            },
        )
        evidence_id = created.json()["data"]["id"]
        replacement = await client.post(
            f"/compliance/evidence/{evidence_id}/supersede",
            params=org(organization_id),
            headers=headers,
            json={"payload": {"v": 2}, "reason": "Stale cache."},
        )
        assert replacement.status_code == HTTP_CREATED
        assert replacement.json()["data"]["supersedes_id"] == evidence_id

        current = await client.get(
            "/compliance/evidence", params=org(organization_id), headers=headers
        )
        assert len(current.json()["data"]) == 1

        everything = await client.get(
            "/compliance/evidence",
            params={**org(organization_id), "include_superseded": "true"},
            headers=headers,
        )
        assert len(everything.json()["data"]) == 2

    async def test_bulk_verification_reports_all_intact(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        await client.post(
            "/compliance/evidence",
            params=org(organization_id),
            headers=headers,
            json={
                "kind": str(EvidenceKind.API_RESPONSE),
                "source": str(EvidenceSource.MONITORING),
                "title": "Metric",
                "payload": {"uptime": 0.999},
            },
        )
        response = await client.get(
            "/compliance/evidence/verify/all", params=org(organization_id), headers=headers
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["failed"] == 0
        assert "all intact" in response.json()["message"]


class TestGovernanceApi:
    async def _control(
        self, client: AsyncClient, headers: dict[str, str], organization_id: uuid.UUID
    ) -> str:
        framework = await client.post(
            "/compliance/frameworks",
            params=org(organization_id),
            headers=headers,
            json={"slug": "cis", "name": "CIS"},
        )
        control = await client.post(
            "/compliance/controls",
            params={
                **org(organization_id),
                "framework_id": str(framework.json()["data"]["id"]),
            },
            headers=headers,
            json={"code": "1.1", "title": "Firewall", **rule_payload()},
        )
        return str(control.json()["data"]["id"])

    async def test_an_exception_is_requested_then_approved(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        control_id = await self._control(client, headers, organization_id)
        created = await client.post(
            "/compliance/exceptions",
            params=org(organization_id),
            headers=headers,
            json={
                "control_id": control_id,
                "title": "Vendor appliance",
                "business_justification": "The firewall is upstream of this device.",
                "expires_at": soon(30).isoformat(),
            },
        )
        assert created.status_code == HTTP_CREATED
        assert created.json()["data"]["status"] == "requested"

        decided = await client.post(
            f"/compliance/exceptions/{created.json()['data']['id']}/decide",
            params=org(organization_id),
            headers=headers,
            json={"approve": True, "decided_by": "ciso"},
        )
        assert decided.json()["data"]["status"] == "active"

    async def test_a_temporary_exception_without_an_expiry_is_a_400(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        control_id = await self._control(client, headers, organization_id)
        response = await client.post(
            "/compliance/exceptions",
            params=org(organization_id),
            headers=headers,
            json={
                "control_id": control_id,
                "title": "Forever",
                "business_justification": "Because.",
            },
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_the_expiring_literal_route_is_reachable(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        # /exceptions/expiring after /exceptions/{exception_id} would be
        # parsed as an exception whose id is the word "expiring".
        response = await client.get(
            "/compliance/exceptions/expiring",
            params=org(organization_id),
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_OK

    async def test_overused_and_due_for_review_are_reachable(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        assert (
            await client.get(
                "/compliance/exceptions/overused", params=org(organization_id), headers=headers
            )
        ).status_code == HTTP_OK
        assert (
            await client.get(
                "/compliance/exceptions/due-for-review",
                params=org(organization_id),
                headers=headers,
            )
        ).status_code == HTTP_OK

    async def test_a_risk_is_registered_with_a_derived_severity(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/compliance/risk-register",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={
                "title": "Unpatched estate",
                "likelihood": str(RiskLikelihood.ALMOST_CERTAIN),
                "impact": str(RiskImpact.SEVERE),
            },
        )
        assert response.status_code == HTTP_CREATED
        data = response.json()["data"]
        assert data["severity"] == "critical"
        assert data["reference"] == "RISK-0001"

    async def test_closing_a_risk_without_a_reason_is_a_400(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        created = await client.post(
            "/compliance/risk-register",
            params=org(organization_id),
            headers=headers,
            json={
                "title": "Closing",
                "likelihood": str(RiskLikelihood.RARE),
                "impact": str(RiskImpact.MINOR),
            },
        )
        response = await client.post(
            f"/compliance/risk-register/{created.json()['data']['id']}/transition",
            params=org(organization_id),
            headers=headers,
            json={"status": str(RiskStatus.CLOSED)},
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_a_finding_cannot_be_marked_verified_over_http(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        # The one status that means *proven* must not be settable by
        # hand, or it comes to mean *asserted*.
        headers = auth_headers(CALLER)
        framework = await client.post(
            "/compliance/frameworks",
            params=org(organization_id),
            headers=headers,
            json={"slug": "cis", "name": "CIS"},
        )
        framework_id = str(framework.json()["data"]["id"])
        await client.post(
            "/compliance/controls",
            params={**org(organization_id), "framework_id": framework_id},
            headers=headers,
            json={"code": "1.1", "title": "Firewall", "severity": "high", **rule_payload()},
        )
        planned = await client.post(
            "/compliance/assessments",
            params=org(organization_id),
            headers=headers,
            json={"name": "Raise one", "framework_id": framework_id},
        )
        await client.post(
            f"/compliance/assessments/{planned.json()['data']['id']}/run",
            params=org(organization_id),
            headers=headers,
            json={
                "targets": [{"target_id": "host-1", "payload": {"firewall": {"enabled": False}}}]
            },
        )
        findings = await client.get(
            "/compliance/findings", params=org(organization_id), headers=headers
        )
        finding_id = findings.json()["data"][0]["id"]

        response = await client.post(
            f"/compliance/findings/{finding_id}/transition",
            params=org(organization_id),
            headers=headers,
            json={"status": str(FindingStatus.VERIFIED)},
        )
        assert response.status_code == HTTP_CONFLICT

    async def test_finding_summary_and_overdue_literals_are_reachable(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        assert (
            await client.get(
                "/compliance/findings/summary", params=org(organization_id), headers=headers
            )
        ).status_code == HTTP_OK
        assert (
            await client.get(
                "/compliance/findings/overdue", params=org(organization_id), headers=headers
            )
        ).status_code == HTTP_OK

    async def test_verifying_an_uncompleted_remediation_is_a_409(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        framework = await client.post(
            "/compliance/frameworks",
            params=org(organization_id),
            headers=headers,
            json={"slug": "cis", "name": "CIS"},
        )
        framework_id = str(framework.json()["data"]["id"])
        await client.post(
            "/compliance/controls",
            params={**org(organization_id), "framework_id": framework_id},
            headers=headers,
            json={"code": "1.1", "title": "Firewall", **rule_payload()},
        )
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
            json={
                "targets": [{"target_id": "host-1", "payload": {"firewall": {"enabled": False}}}]
            },
        )
        findings = await client.get(
            "/compliance/findings", params=org(organization_id), headers=headers
        )
        finding_id = findings.json()["data"][0]["id"]

        task = await client.post(
            "/compliance/remediation",
            params=org(organization_id),
            headers=headers,
            json={"finding_id": finding_id, "title": "Enable the firewall"},
        )
        assert task.status_code == HTTP_CREATED

        response = await client.post(
            f"/compliance/remediation/{task.json()['data']['id']}/verify",
            params=org(organization_id),
            headers=headers,
            json={"verified_by": "alice"},
        )
        assert response.status_code == HTTP_CONFLICT


class TestAnalyticsApi:
    async def test_the_dashboard_answers_with_no_data(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/compliance/statistics", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["score"] is None

    async def test_no_score_yet_reads_as_an_empty_object_with_a_hint(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/compliance/scores", params=org(organization_id), headers=auth_headers(CALLER)
        )
        assert response.json()["data"] == {}
        assert "run an assessment" in response.json()["message"].lower()

    async def test_score_history_and_framework_scores_are_reachable(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        assert (
            await client.get(
                "/compliance/scores/history", params=org(organization_id), headers=headers
            )
        ).status_code == HTTP_OK
        assert (
            await client.get(
                "/compliance/scores/frameworks", params=org(organization_id), headers=headers
            )
        ).status_code == HTTP_OK

    async def test_a_rollup_can_be_triggered(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/compliance/statistics/rollup",
            params=org(organization_id),
            headers=auth_headers(CALLER),
        )
        assert response.status_code == HTTP_OK

    @pytest.mark.parametrize("kind", [str(one) for one in ReportKind])
    async def test_every_report_kind_generates_over_http(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        organization_id: uuid.UUID,
        kind: str,
    ) -> None:
        response = await client.post(
            "/compliance/reports",
            params=org(organization_id),
            headers=auth_headers(CALLER),
            json={"kind": kind},
        )
        assert response.status_code == HTTP_CREATED, response.text
        assert response.json()["data"]["error"] is None

    async def test_a_report_downloads_as_csv(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        await client.post(
            "/compliance/frameworks/seed", params=org(organization_id), headers=headers
        )
        created = await client.post(
            "/compliance/reports",
            params=org(organization_id),
            headers=headers,
            json={"kind": str(ReportKind.CONTROL), "report_format": "csv"},
        )
        report_id = created.json()["data"]["id"]
        download = await client.get(
            f"/compliance/reports/{report_id}/download",
            params=org(organization_id),
            headers=headers,
        )
        assert download.status_code == HTTP_OK
        assert download.headers["content-type"].startswith("text/csv")
        assert "code,title" in download.text

    async def test_a_report_downloads_as_markdown_and_json(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        await client.post(
            "/compliance/frameworks/seed", params=org(organization_id), headers=headers
        )
        for fmt, media in (("markdown", "text/markdown"), ("json", "application/json")):
            created = await client.post(
                "/compliance/reports",
                params=org(organization_id),
                headers=headers,
                json={"kind": str(ReportKind.CONTROL), "report_format": fmt},
            )
            download = await client.get(
                f"/compliance/reports/{created.json()['data']['id']}/download",
                params=org(organization_id),
                headers=headers,
            )
            assert download.headers["content-type"].startswith(media)

    async def test_the_audit_trail_is_readable_and_summarisable(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(CALLER)
        await client.post(
            "/compliance/frameworks",
            params=org(organization_id),
            headers=headers,
            json={"slug": "audited", "name": "Audited"},
        )
        entries = await client.get(
            "/compliance/audit", params=org(organization_id), headers=headers
        )
        assert entries.status_code == HTTP_OK
        assert len(entries.json()["data"]) >= 1

        summary = await client.get(
            "/compliance/audit/summary", params=org(organization_id), headers=headers
        )
        assert summary.json()["data"]["total"] >= 1
