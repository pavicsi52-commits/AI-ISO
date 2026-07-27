"""Tests for the ``/workflows`` router."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


def _create_body(organization_id: uuid.UUID, workflow_key: str = "deploy-app") -> dict[str, object]:
    return {
        "organization_id": str(organization_id),
        "workflow_key": workflow_key,
        "name": "Deploy App",
        "description": "Deploys the app.",
        "nodes": [
            {"node_id": "start", "node_type": "start", "name": "start"},
            {"node_id": "end", "node_type": "end", "name": "end"},
        ],
        "edges": [{"from_node_id": "start", "to_node_id": "end"}],
    }


class TestWorkflowsApi:
    async def test_create_then_get_workflow(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        create_response = await client.post(
            "/workflows", json=_create_body(org_id), headers=headers
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]
        assert create_response.json()["data"]["current_version_number"] == "1.0.0"

        get_response = await client.get(f"/workflows/{workflow_id}", headers=headers)
        assert get_response.status_code == 200
        assert get_response.json()["data"]["workflow_key"] == "deploy-app"

    async def test_create_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post("/workflows", json=_create_body(uuid.uuid4()))
        assert response.status_code == 401

    async def test_create_duplicate_workflow_key_returns_conflict(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        await client.post("/workflows", json=_create_body(org_id), headers=headers)
        response = await client.post("/workflows", json=_create_body(org_id), headers=headers)
        assert response.status_code == 409

    async def test_list_workflows_filters_by_org(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        await client.post("/workflows", json=_create_body(org_id), headers=headers)

        response = await client.get(
            "/workflows", params={"organization_id": str(org_id)}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_update_workflow_bumps_version(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post("/workflows", json=_create_body(org_id), headers=headers)
        workflow_id = created.json()["data"]["id"]

        response = await client.put(
            f"/workflows/{workflow_id}",
            json={
                "name": "Deploy App Renamed",
                "nodes": [
                    {"node_id": "start", "node_type": "start", "name": "start"},
                    {"node_id": "end", "node_type": "end", "name": "end"},
                ],
                "edges": [{"from_node_id": "start", "to_node_id": "end"}],
            },
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Deploy App Renamed"
        assert response.json()["data"]["current_version_number"] == "1.0.1"

    async def test_delete_workflow(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post("/workflows", json=_create_body(org_id), headers=headers)
        workflow_id = created.json()["data"]["id"]

        delete_response = await client.delete(f"/workflows/{workflow_id}", headers=headers)
        assert delete_response.status_code == 200

        get_response = await client.get(f"/workflows/{workflow_id}", headers=headers)
        assert get_response.status_code == 404

    async def test_execute_workflow_enqueues_instance(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post("/workflows", json=_create_body(org_id), headers=headers)
        workflow_id = created.json()["data"]["id"]

        response = await client.post(
            f"/workflows/{workflow_id}/execute", json={"variables": {}}, headers=headers
        )
        assert response.status_code == 201
        assert response.json()["data"]["status"] == "queued"

    async def test_pause_resume_cancel_active_instance(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post("/workflows", json=_create_body(org_id), headers=headers)
        workflow_id = created.json()["data"]["id"]
        await client.post(
            f"/workflows/{workflow_id}/execute", json={"variables": {}}, headers=headers
        )

        pause_response = await client.post(f"/workflows/{workflow_id}/pause", headers=headers)
        assert pause_response.status_code == 200
        assert pause_response.json()["data"]["status"] == "paused"

        resume_response = await client.post(f"/workflows/{workflow_id}/resume", headers=headers)
        assert resume_response.status_code == 200
        assert resume_response.json()["data"]["status"] == "running"

        cancel_response = await client.post(f"/workflows/{workflow_id}/cancel", headers=headers)
        assert cancel_response.status_code == 200
        assert cancel_response.json()["data"]["status"] == "cancelled"

    async def test_pause_with_no_active_instance_returns_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post("/workflows", json=_create_body(org_id), headers=headers)
        workflow_id = created.json()["data"]["id"]

        response = await client.post(f"/workflows/{workflow_id}/pause", headers=headers)
        assert response.status_code == 404

    async def test_get_missing_workflow_returns_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        response = await client.get(f"/workflows/{uuid.uuid4()}", headers=headers)
        assert response.status_code == 404

    async def test_rollback_active_instance_with_no_completed_steps(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post("/workflows", json=_create_body(org_id), headers=headers)
        workflow_id = created.json()["data"]["id"]
        await client.post(
            f"/workflows/{workflow_id}/execute", json={"variables": {}}, headers=headers
        )

        response = await client.post(
            f"/workflows/{workflow_id}/rollback", json={"rollback_type": "manual"}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["data"]["compensated_node_ids"] == []

    async def test_replay_active_instance_creates_new_instance(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post("/workflows", json=_create_body(org_id), headers=headers)
        workflow_id = created.json()["data"]["id"]
        executed = await client.post(
            f"/workflows/{workflow_id}/execute", json={"variables": {}}, headers=headers
        )
        original_instance_id = executed.json()["data"]["id"]

        response = await client.post(
            f"/workflows/{workflow_id}/replay", json={"replay_type": "full"}, headers=headers
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["instance_id"] == original_instance_id
        assert data["new_instance_id"] != original_instance_id
