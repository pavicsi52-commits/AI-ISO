"""Tests for the ``/automation/reports`` router."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


class TestReportsRouter:
    async def test_generate_executive_dashboard_report(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        org_id = uuid.uuid4()
        response = await client.get(
            "/automation/reports",
            params={"organization_id": str(org_id), "report_type": "executive_dashboard"},
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == 200
        assert "total_jobs" in response.json()["data"]["result"]

    async def test_generate_execution_report_requires_job_id(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        org_id = uuid.uuid4()
        response = await client.get(
            "/automation/reports",
            params={"organization_id": str(org_id), "report_type": "execution"},
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == 400

    async def test_generate_report_requires_auth(self, client: AsyncClient) -> None:
        response = await client.get(
            "/automation/reports",
            params={
                "organization_id": str(uuid.uuid4()),
                "report_type": "executive_dashboard",
            },
        )
        assert response.status_code == 401
