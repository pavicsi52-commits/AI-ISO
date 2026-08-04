"""HTTP tests for /changes -- changes, relationships, risk, and approvals.

Routes whose handler declares a ``caller: CurrentUserId`` parameter
(create/update/submit/schedule/cancel/close, ``assess_risk``,
``decide_approval``) need ``Authorization`` headers; relationships,
listing, overriding, requesting approvals, and delegating do not.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from tests.conftest import (
    HTTP_BAD_REQUEST,
    HTTP_CONFLICT,
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
    soon,
)

pytestmark = pytest.mark.asyncio


async def _create_change(
    client: AsyncClient, headers: dict[str, str], organization_id: uuid.UUID, **overrides: object
) -> dict:
    payload = {"title": "Patch the payments gateway", "requester_id": "requester-1", **overrides}
    resp = await client.post(
        "/changes", params={"organization_id": str(organization_id)}, headers=headers, json=payload
    )
    assert resp.status_code == HTTP_CREATED, resp.text
    return resp.json()["data"]


_MINOR_DIMENSIONS = {
    "technical": "minor",
    "business": "minor",
    "operational": "minor",
    "security": "minor",
    "compliance": "minor",
    "dependency": "minor",
}


class TestCreateGetList:
    async def test_create_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/changes",
            params={"organization_id": str(organization_id)},
            json={"title": "x", "requester_id": "r1"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_create_returns_the_new_change(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        data = await _create_change(client, auth_headers(uuid.uuid4()), organization_id)
        assert data["reference"].startswith("CHG-")
        assert data["status"] == "draft"
        assert data["title"] == "Patch the payments gateway"

    async def test_create_missing_title_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/changes",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"requester_id": "requester-1"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_get_returns_the_change(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_change(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.get(
            f"/changes/{created['id']}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == created["id"]

    async def test_get_returns_404_for_a_missing_change(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/changes/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_list_finds_the_created_change(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_change(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.get("/changes", params={"organization_id": str(organization_id)})
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert created["id"] in ids

    async def test_list_filters_by_status(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_change(client, auth_headers(uuid.uuid4()), organization_id)
        matching = await client.get(
            "/changes", params={"organization_id": str(organization_id), "status": "draft"}
        )
        assert created["id"] in {one["id"] for one in matching.json()["data"]}
        non_matching = await client.get(
            "/changes", params={"organization_id": str(organization_id), "status": "cancelled"}
        )
        assert created["id"] not in {one["id"] for one in non_matching.json()["data"]}


class TestUpdate:
    async def test_update_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_change(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.put(
            f"/changes/{created['id']}",
            params={"organization_id": str(organization_id)},
            json={"title": "New title"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_update_edits_a_draft_change(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_change(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.put(
            f"/changes/{created['id']}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"title": "Patch the payments gateway (v2)"},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["title"] == "Patch the payments gateway (v2)"

    async def test_update_after_submit_is_refused(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _create_change(client, headers, organization_id)
        await client.post(
            f"/changes/{created['id']}/submit",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        resp = await client.put(
            f"/changes/{created['id']}",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"title": "Too late"},
        )
        assert resp.status_code == HTTP_CONFLICT


class TestLifecycleTransitions:
    async def test_submit_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_change(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.post(
            f"/changes/{created['id']}/submit", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_submit_moves_to_submitted(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _create_change(client, headers, organization_id)
        resp = await client.post(
            f"/changes/{created['id']}/submit",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["status"] == "submitted"
        assert data["submitted_at"] is not None

    async def test_schedule_moves_to_scheduled(
        self,
        client: AsyncClient,
        auth_headers,
        organization_id: uuid.UUID,
        make_approved_change,
        calendar_service,
    ) -> None:
        change = await make_approved_change()
        entry = await calendar_service.create_entry(
            organization_id,
            kind="maintenance_window",
            title="Test maintenance window",
            starts_at=soon(1),
            ends_at=soon(2),
        )
        resp = await client.post(
            f"/changes/{change.id}/schedule",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "calendar_entry_id": str(entry.id),
                "scheduled_start_at": soon(1).isoformat(),
                "scheduled_end_at": soon(2).isoformat(),
            },
        )
        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["status"] == "scheduled"
        assert data["calendar_entry_id"] == str(entry.id)

    async def test_schedule_with_a_missing_calendar_entry_is_404(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_approved_change
    ) -> None:
        change = await make_approved_change()
        resp = await client.post(
            f"/changes/{change.id}/schedule",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "calendar_entry_id": str(uuid.uuid4()),
                "scheduled_start_at": soon(1).isoformat(),
                "scheduled_end_at": soon(2).isoformat(),
            },
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_cancel_a_draft_change(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _create_change(client, headers, organization_id)
        resp = await client.post(
            f"/changes/{created['id']}/cancel",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["status"] == "cancelled"

    async def test_cancel_a_completed_change_is_refused(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_completed_change
    ) -> None:
        change = await make_completed_change()
        resp = await client.post(
            f"/changes/{change.id}/cancel",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_close_a_completed_change(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_completed_change
    ) -> None:
        change = await make_completed_change()
        resp = await client.post(
            f"/changes/{change.id}/close",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["status"] == "closed"
        assert data["closed_at"] is not None

    async def test_close_a_draft_change_is_refused(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _create_change(client, headers, organization_id)
        resp = await client.post(
            f"/changes/{created['id']}/close",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        assert resp.status_code == HTTP_BAD_REQUEST


class TestRelationships:
    async def test_link_returns_the_new_relationship(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        source = await _create_change(client, headers, organization_id, title="Source change")
        target = await _create_change(client, headers, organization_id, title="Target change")
        resp = await client.post(
            f"/changes/{source['id']}/relationships",
            params={"organization_id": str(organization_id)},
            json={
                "related_change_id": target["id"],
                "kind": "depends_on",
                "note": "Needs the schema migration first.",
            },
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["change_id"] == source["id"]
        assert data["related_change_id"] == target["id"]
        assert data["kind"] == "depends_on"

    async def test_link_to_self_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_change(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.post(
            f"/changes/{created['id']}/relationships",
            params={"organization_id": str(organization_id)},
            json={"related_change_id": created["id"], "kind": "related_to"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_link_to_a_missing_change_is_404(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_change(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.post(
            f"/changes/{created['id']}/relationships",
            params={"organization_id": str(organization_id)},
            json={"related_change_id": str(uuid.uuid4()), "kind": "related_to"},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_list_relationships_finds_it(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        source = await _create_change(client, headers, organization_id, title="Source change")
        target = await _create_change(client, headers, organization_id, title="Target change")
        await client.post(
            f"/changes/{source['id']}/relationships",
            params={"organization_id": str(organization_id)},
            json={"related_change_id": target["id"], "kind": "blocks"},
        )
        resp = await client.get(
            f"/changes/{source['id']}/relationships",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        rows = resp.json()["data"]
        assert len(rows) == 1
        assert rows[0]["related_change_id"] == target["id"]


class TestRiskAssessments:
    async def test_assess_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _create_change(client, headers, organization_id)
        await client.post(
            f"/changes/{created['id']}/submit",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        resp = await client.post(
            f"/changes/{created['id']}/risk-assessments",
            params={"organization_id": str(organization_id)},
            json={"likelihood": "possible", "dimensions": _MINOR_DIMENSIONS},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_assess_returns_the_new_assessment(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _create_change(client, headers, organization_id)
        await client.post(
            f"/changes/{created['id']}/submit",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        resp = await client.post(
            f"/changes/{created['id']}/risk-assessments",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={
                "likelihood": "possible",
                "dimensions": _MINOR_DIMENSIONS,
                "assessed_by": "assessor-1",
            },
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["change_id"] == created["id"]
        assert data["risk_level"] == "medium"
        assert data["assessed_by"] == "assessor-1"

    async def test_assess_before_submit_is_refused(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _create_change(client, headers, organization_id)
        resp = await client.post(
            f"/changes/{created['id']}/risk-assessments",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"likelihood": "possible", "dimensions": _MINOR_DIMENSIONS},
        )
        assert resp.status_code == HTTP_CONFLICT

    async def test_list_finds_the_assessment(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _create_change(client, headers, organization_id)
        await client.post(
            f"/changes/{created['id']}/submit",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        assessed = await client.post(
            f"/changes/{created['id']}/risk-assessments",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"likelihood": "possible", "dimensions": _MINOR_DIMENSIONS},
        )
        resp = await client.get(
            f"/changes/{created['id']}/risk-assessments",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert assessed.json()["data"]["id"] in ids

    async def test_override_updates_the_banding(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _create_change(client, headers, organization_id)
        await client.post(
            f"/changes/{created['id']}/submit",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        assessed = await client.post(
            f"/changes/{created['id']}/risk-assessments",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"likelihood": "possible", "dimensions": _MINOR_DIMENSIONS},
        )
        assessment_id = assessed.json()["data"]["id"]
        resp = await client.post(
            f"/changes/risk-assessments/{assessment_id}/override",
            params={"organization_id": str(organization_id)},
            json={
                "override": "high",
                "reason": "Underlying dependency turned out to be shared infrastructure.",
                "by": "reviewer-1",
            },
        )
        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["manual_override"] == "high"
        assert data["override_by"] == "reviewer-1"

    async def test_override_returns_404_for_a_missing_assessment(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/changes/risk-assessments/{uuid.uuid4()}/override",
            params={"organization_id": str(organization_id)},
            json={"override": "high", "reason": "n/a", "by": "reviewer-1"},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestApprovals:
    async def test_request_returns_the_chain(
        self, client: AsyncClient, organization_id: uuid.UUID, make_assessed_change
    ) -> None:
        change = await make_assessed_change()
        resp = await client.post(
            f"/changes/{change.id}/approvals",
            params={"organization_id": str(organization_id)},
            json={
                "policy": "single",
                "approvers": [{"approver_id": "approver-1", "approver_role": "change-manager"}],
            },
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        rows = resp.json()["data"]
        assert len(rows) == 1
        assert rows[0]["status"] == "pending"
        assert rows[0]["approver_id"] == "approver-1"

    async def test_request_before_pending_approval_is_refused(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_change(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.post(
            f"/changes/{created['id']}/approvals",
            params={"organization_id": str(organization_id)},
            json={"policy": "single", "approvers": [{"approver_id": "approver-1"}]},
        )
        assert resp.status_code == HTTP_CONFLICT

    async def test_request_with_too_few_approvers_is_refused(
        self, client: AsyncClient, organization_id: uuid.UUID, make_assessed_change
    ) -> None:
        change = await make_assessed_change()
        resp = await client.post(
            f"/changes/{change.id}/approvals",
            params={"organization_id": str(organization_id)},
            json={"policy": "multi_level", "approvers": [{"approver_id": "approver-1"}]},
        )
        assert resp.status_code == HTTP_CONFLICT

    async def test_list_finds_the_chain(
        self, client: AsyncClient, organization_id: uuid.UUID, make_assessed_change
    ) -> None:
        change = await make_assessed_change()
        await client.post(
            f"/changes/{change.id}/approvals",
            params={"organization_id": str(organization_id)},
            json={"policy": "single", "approvers": [{"approver_id": "approver-1"}]},
        )
        resp = await client.get(
            f"/changes/{change.id}/approvals", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert len(resp.json()["data"]) == 1

    async def test_decide_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID, make_assessed_change
    ) -> None:
        change = await make_assessed_change()
        requested = await client.post(
            f"/changes/{change.id}/approvals",
            params={"organization_id": str(organization_id)},
            json={"policy": "single", "approvers": [{"approver_id": "approver-1"}]},
        )
        approval_id = requested.json()["data"][0]["id"]
        resp = await client.post(
            f"/changes/approvals/{approval_id}/decide",
            params={"organization_id": str(organization_id)},
            json={"decision": "approved"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_decide_records_the_decision(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_assessed_change
    ) -> None:
        change = await make_assessed_change()
        requested = await client.post(
            f"/changes/{change.id}/approvals",
            params={"organization_id": str(organization_id)},
            json={"policy": "single", "approvers": [{"approver_id": "approver-1"}]},
        )
        approval_id = requested.json()["data"][0]["id"]
        resp = await client.post(
            f"/changes/approvals/{approval_id}/decide",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"decision": "approved", "comment": "Looks good."},
        )
        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["status"] == "approved"
        assert data["comment"] == "Looks good."

    async def test_decide_returns_404_for_a_missing_approval(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/changes/approvals/{uuid.uuid4()}/decide",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"decision": "approved"},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_deciding_twice_is_refused(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_assessed_change
    ) -> None:
        change = await make_assessed_change()
        requested = await client.post(
            f"/changes/{change.id}/approvals",
            params={"organization_id": str(organization_id)},
            json={"policy": "single", "approvers": [{"approver_id": "approver-1"}]},
        )
        approval_id = requested.json()["data"][0]["id"]
        headers = auth_headers(uuid.uuid4())
        await client.post(
            f"/changes/approvals/{approval_id}/decide",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"decision": "approved"},
        )
        resp = await client.post(
            f"/changes/approvals/{approval_id}/decide",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"decision": "approved"},
        )
        assert resp.status_code == HTTP_CONFLICT

    async def test_delegate_reassigns_a_pending_step(
        self, client: AsyncClient, organization_id: uuid.UUID, make_assessed_change
    ) -> None:
        change = await make_assessed_change()
        requested = await client.post(
            f"/changes/{change.id}/approvals",
            params={"organization_id": str(organization_id)},
            json={"policy": "single", "approvers": [{"approver_id": "approver-1"}]},
        )
        approval_id = requested.json()["data"][0]["id"]
        resp = await client.post(
            f"/changes/approvals/{approval_id}/delegate",
            params={"organization_id": str(organization_id)},
            json={"delegated_to": "approver-2"},
        )
        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["approver_id"] == "approver-2"
        assert data["delegated_from"] == "approver-1"
        assert data["status"] == "pending"

    async def test_delegate_returns_404_for_a_missing_approval(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/changes/approvals/{uuid.uuid4()}/delegate",
            params={"organization_id": str(organization_id)},
            json={"delegated_to": "approver-2"},
        )
        assert resp.status_code == HTTP_NOT_FOUND
