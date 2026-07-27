"""Tests for the ``/workflow/reports`` router."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


class TestReportsApi:
    async def test_generate_performance_report(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()

        response = await client.get(
            "/workflow/reports",
            params={"organization_id": str(org_id), "report_type": "performance"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["report_type"] == "performance"
        assert "success_rate" in response.json()["data"]["result"]

    async def test_generate_executive_dashboard_report(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()

        response = await client.get(
            "/workflow/reports",
            params={"organization_id": str(org_id), "report_type": "executive_dashboard"},
            headers=headers,
        )
        assert response.status_code == 200
        assert "total_workflows" in response.json()["data"]["result"]

    async def test_generate_execution_report_for_instance(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post(
            "/workflows",
            json={
                "organization_id": str(org_id),
                "workflow_key": "deploy-app",
                "name": "Deploy App",
                "nodes": [
                    {"node_id": "start", "node_type": "start", "name": "start"},
                    {"node_id": "end", "node_type": "end", "name": "end"},
                ],
                "edges": [{"from_node_id": "start", "to_node_id": "end"}],
            },
            headers=headers,
        )
        workflow_id = created.json()["data"]["id"]
        executed = await client.post(
            f"/workflows/{workflow_id}/execute", json={"variables": {}}, headers=headers
        )
        instance_id = executed.json()["data"]["id"]

        response = await client.get(
            "/workflow/reports",
            params={
                "organization_id": str(org_id),
                "report_type": "execution",
                "instance_id": instance_id,
            },
            headers=headers,
        )
        assert response.status_code == 200
        assert "total_steps" in response.json()["data"]["result"]

    async def test_execution_report_without_instance_id_returns_400(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())

        response = await client.get(
            "/workflow/reports",
            params={"organization_id": str(uuid.uuid4()), "report_type": "execution"},
            headers=headers,
        )
        assert response.status_code == 400

    async def test_generate_report_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get(
            "/workflow/reports",
            params={"organization_id": str(uuid.uuid4()), "report_type": "performance"},
        )
        assert response.status_code == 401
