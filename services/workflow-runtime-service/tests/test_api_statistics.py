"""Tests for the ``/workflow/statistics`` router."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


class TestStatisticsApi:
    async def test_get_statistics_for_org_with_no_data(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()

        response = await client.get(
            "/workflow/statistics", params={"organization_id": str(org_id)}, headers=headers
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total_workflows"] == 0
        assert data["total_executions"] == 0

    async def test_get_statistics_reflects_created_workflow(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        await client.post(
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

        response = await client.get(
            "/workflow/statistics", params={"organization_id": str(org_id)}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["data"]["total_workflows"] == 1

    async def test_get_statistics_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get(
            "/workflow/statistics", params={"organization_id": str(uuid.uuid4())}
        )
        assert response.status_code == 401
