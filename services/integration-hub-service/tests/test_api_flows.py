"""HTTP tests for /integrations/flows.

Only `run` declares a `caller: CurrentUserId` dependency and needs
`Authorization` headers -- it writes an audit entry under the caller's own
actor id. Every other route (list/get/create/activate/disable/approve)
takes no `CurrentUserId` dependency at all -- confirmed by reading
`app/api/flows.py` directly, not assumed.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import (
    HTTP_BAD_REQUEST,
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
    AuthHeadersFn,
)

pytestmark = pytest.mark.asyncio


def _noop_definition() -> dict:
    return {"start": "s1", "steps": {"s1": {"kind": "action", "action": "noop", "next": None}}}


async def _create_flow(client: AsyncClient, organization_id: uuid.UUID, **overrides: object) -> dict:
    payload = {"name": "api-flow", "definition": _noop_definition(), **overrides}
    resp = await client.post(
        "/integrations/flows", params={"organization_id": str(organization_id)}, json=payload
    )
    assert resp.status_code == HTTP_CREATED, resp.text
    return resp.json()["data"]


async def _activate(client: AsyncClient, organization_id: uuid.UUID, flow_id: str) -> None:
    resp = await client.post(
        f"/integrations/flows/{flow_id}/activate", params={"organization_id": str(organization_id)}
    )
    assert resp.status_code == HTTP_OK, resp.text


class TestCreateAndGet:
    async def test_create_does_not_require_auth(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        data = await _create_flow(client, organization_id)
        assert data["status"] == "draft"
        assert data["enabled"] is False
        assert data["run_count"] == 0

    async def test_create_persists_the_definition(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        definition = _noop_definition()
        data = await _create_flow(client, organization_id, name="named-flow", definition=definition)
        assert data["name"] == "named-flow"
        assert data["definition"] == definition

    async def test_get_returns_the_created_flow(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        created = await _create_flow(client, organization_id)
        resp = await client.get(
            f"/integrations/flows/{created['id']}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == created["id"]

    async def test_get_returns_404_for_a_missing_flow(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/integrations/flows/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_get_is_isolated_across_organizations(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        created = await _create_flow(client, organization_id)
        resp = await client.get(
            f"/integrations/flows/{created['id']}", params={"organization_id": str(uuid.uuid4())}
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_list_finds_the_created_flow(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        created = await _create_flow(client, organization_id)
        resp = await client.get(
            "/integrations/flows", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        ids = {row["id"] for row in resp.json()["data"]}
        assert created["id"] in ids


class TestActivateDisable:
    async def test_activate_moves_to_active(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        created = await _create_flow(client, organization_id)
        resp = await client.post(
            f"/integrations/flows/{created['id']}/activate",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["status"] == "active"
        assert data["enabled"] is True

    async def test_disable_moves_to_disabled(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        created = await _create_flow(client, organization_id)
        await _activate(client, organization_id, created["id"])
        resp = await client.post(
            f"/integrations/flows/{created['id']}/disable",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["status"] == "disabled"
        assert data["enabled"] is False

    async def test_activate_returns_404_for_a_missing_flow(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/integrations/flows/{uuid.uuid4()}/activate",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestRun:
    async def test_run_requires_auth(self, client: AsyncClient, organization_id: uuid.UUID) -> None:
        created = await _create_flow(client, organization_id)
        await _activate(client, organization_id, created["id"])
        resp = await client.post(
            f"/integrations/flows/{created['id']}/run",
            params={"organization_id": str(organization_id)},
            json={"context": {}},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_run_rejects_a_draft_flow(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        created = await _create_flow(client, organization_id)
        resp = await client.post(
            f"/integrations/flows/{created['id']}/run",
            params={"organization_id": str(organization_id)},
            json={"context": {}},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_run_executes_a_noop_flow(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        created = await _create_flow(client, organization_id)
        await _activate(client, organization_id, created["id"])
        resp = await client.post(
            f"/integrations/flows/{created['id']}/run",
            params={"organization_id": str(organization_id)},
            json={"context": {}},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["status"] == "succeeded"
        assert data["steps_executed"] == ["s1"]
        assert data["error"] is None

    async def test_run_executes_a_sync_step_against_real_context_records(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        organization_id: uuid.UUID,
        make_connector,
        sync_jobs_repo,
    ) -> None:
        connector = await make_connector("api-sync-target")
        definition = {
            "start": "s1",
            "steps": {"s1": {"kind": "action", "action": "sync", "config": {}, "next": None}},
        }
        created = await _create_flow(client, organization_id, definition=definition)
        await _activate(client, organization_id, created["id"])

        resp = await client.post(
            f"/integrations/flows/{created['id']}/run",
            params={"organization_id": str(organization_id)},
            json={
                "context": {
                    "connector_id": str(connector.id),
                    "records": [{"id": 1}, {"id": 2}, {"id": 3}],
                }
            },
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["status"] == "succeeded"
        assert data["context"]["sync_status"] == "completed"

        jobs = await sync_jobs_repo.list_for_org(organization_id)
        assert len(jobs) == 1
        assert jobs[0].connector_id == connector.id
        assert jobs[0].records_succeeded == 3

    async def test_run_records_an_audit_entry(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        created = await _create_flow(client, organization_id)
        await _activate(client, organization_id, created["id"])
        await client.post(
            f"/integrations/flows/{created['id']}/run",
            params={"organization_id": str(organization_id)},
            json={"context": {}},
            headers=auth_headers(uuid.uuid4()),
        )
        audit = await client.get(
            "/integrations/audit", params={"organization_id": str(organization_id)}
        )
        assert audit.status_code == HTTP_OK
        actions = {row["action"] for row in audit.json()["data"]}
        assert "flow_executed" in actions


class TestApprove:
    async def test_run_pauses_on_approval_then_approve_resumes_it(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        definition = {
            "start": "s1",
            "steps": {
                "s1": {"kind": "approval", "next": "s2"},
                "s2": {"kind": "action", "action": "noop", "next": None},
            },
        }
        created = await _create_flow(client, organization_id, definition=definition)
        await _activate(client, organization_id, created["id"])

        paused = await client.post(
            f"/integrations/flows/{created['id']}/run",
            params={"organization_id": str(organization_id)},
            json={"context": {}},
            headers=auth_headers(uuid.uuid4()),
        )
        assert paused.status_code == HTTP_OK
        paused_data = paused.json()["data"]
        assert paused_data["status"] == "awaiting_approval"
        assert paused_data["awaiting_step"] == "s1"

        approved = await client.post(
            f"/integrations/flows/{created['id']}/approve/s1",
            params={"organization_id": str(organization_id)},
            json={"context": {}},
        )
        assert approved.status_code == HTTP_OK
        approved_data = approved.json()["data"]
        assert approved_data["status"] == "succeeded"
        assert approved_data["steps_executed"] == ["s1", "s2"]
        assert approved_data["awaiting_step"] is None

    async def test_approve_does_not_require_auth(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        definition = {"start": "s1", "steps": {"s1": {"kind": "approval", "next": None}}}
        created = await _create_flow(client, organization_id, definition=definition)
        await _activate(client, organization_id, created["id"])
        resp = await client.post(
            f"/integrations/flows/{created['id']}/approve/s1",
            params={"organization_id": str(organization_id)},
            json={"context": {}},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["status"] == "succeeded"

    async def test_approve_returns_404_for_a_missing_flow(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/integrations/flows/{uuid.uuid4()}/approve/s1",
            params={"organization_id": str(organization_id)},
            json={"context": {}},
        )
        assert resp.status_code == HTTP_NOT_FOUND
