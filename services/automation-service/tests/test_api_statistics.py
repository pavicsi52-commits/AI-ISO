"""Tests for the ``/automation/statistics`` router."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


class TestStatisticsRouter:
    async def test_get_statistics_for_empty_org(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        org_id = uuid.uuid4()
        response = await client.get(
            "/automation/statistics",
            params={"organization_id": str(org_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["total_jobs"] == 0
        assert body["total_executions"] == 0

    async def test_get_statistics_requires_auth(self, client: AsyncClient) -> None:
        response = await client.get(
            "/automation/statistics", params={"organization_id": str(uuid.uuid4())}
        )
        assert response.status_code == 401
