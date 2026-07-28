"""Tests for the ``/monitoring/reports`` and ``/monitoring/statistics`` routers."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


class TestMonitoringReportsApi:
    async def test_generate_org_scoped_report(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        response = await client.get(
            "/monitoring/reports",
            params={"organization_id": str(uuid.uuid4()), "report_type": "executive"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["report_type"] == "executive"

    async def test_generate_target_scoped_report(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        target = await client.post(
            "/monitoring/targets",
            json={
                "organization_id": str(org_id),
                "target_type": "physical_server",
                "external_id": "report-target",
                "name": "Report Target",
            },
            headers=headers,
        )
        target_id = target.json()["data"]["id"]
        response = await client.get(
            "/monitoring/reports",
            params={
                "organization_id": str(org_id),
                "report_type": "health",
                "target_id": target_id,
            },
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["target_id"] == target_id

    async def test_target_scoped_without_target_id_returns_error(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        response = await client.get(
            "/monitoring/reports",
            params={"organization_id": str(uuid.uuid4()), "report_type": "health"},
            headers=headers,
        )
        assert response.status_code == 400

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get(
            "/monitoring/reports",
            params={"organization_id": str(uuid.uuid4()), "report_type": "executive"},
        )
        assert response.status_code == 401


class TestMonitoringStatisticsApi:
    async def test_get_statistics_for_org_with_no_data(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        response = await client.get(
            "/monitoring/statistics", params={"organization_id": str(uuid.uuid4())}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["data"]["total_targets"] == 0

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get(
            "/monitoring/statistics", params={"organization_id": str(uuid.uuid4())}
        )
        assert response.status_code == 401
