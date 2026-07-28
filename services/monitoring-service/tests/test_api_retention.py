"""Tests for the ``/monitoring-retention-policies`` router."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


class TestMonitoringRetentionApi:
    async def test_create_then_list(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post(
            "/monitoring-retention-policies",
            json={
                "organization_id": str(org_id),
                "metric_type": "cpu_usage",
                "retention_days": 30,
            },
            headers=headers,
        )
        assert created.status_code == 201

        response = await client.get(
            "/monitoring-retention-policies",
            params={"organization_id": str(org_id)},
            headers=headers,
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_create_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(
            "/monitoring-retention-policies",
            json={"organization_id": str(uuid.uuid4()), "retention_days": 30},
        )
        assert response.status_code == 401
