"""Tests for the ``/monitoring/metrics`` router."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


class TestMonitoringMetricsApi:
    async def test_create_then_list_then_get(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post(
            "/monitoring/metrics",
            json={
                "organization_id": str(org_id),
                "metric_type": "cpu_usage",
                "name": "cpu_usage_percent",
                "unit": "percent",
            },
            headers=headers,
        )
        assert created.status_code == 201
        metric_id = created.json()["data"]["id"]

        listed = await client.get(
            "/monitoring/metrics", params={"organization_id": str(org_id)}, headers=headers
        )
        assert listed.status_code == 200
        assert len(listed.json()["data"]) == 1

        fetched = await client.get(f"/monitoring/metrics/{metric_id}", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["data"]["name"] == "cpu_usage_percent"

    async def test_get_missing_metric_returns_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        response = await client.get(f"/monitoring/metrics/{uuid.uuid4()}", headers=headers)
        assert response.status_code == 404

    async def test_get_series_for_target(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        target = await client.post(
            "/monitoring/targets",
            json={
                "organization_id": str(org_id),
                "target_type": "physical_server",
                "external_id": "series-target",
                "name": "Series Target",
            },
            headers=headers,
        )
        target_id = target.json()["data"]["id"]
        metric = await client.post(
            "/monitoring/metrics",
            json={
                "organization_id": str(org_id),
                "metric_type": "latency",
                "name": "latency_ms",
            },
            headers=headers,
        )
        metric_id = metric.json()["data"]["id"]

        series = await client.get(
            f"/monitoring/metrics/{metric_id}/series",
            params={"target_id": target_id},
            headers=headers,
        )
        assert series.status_code == 200
        assert series.json()["data"] == []

    async def test_create_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(
            "/monitoring/metrics",
            json={
                "organization_id": str(uuid.uuid4()),
                "metric_type": "cpu_usage",
                "name": "x",
            },
        )
        assert response.status_code == 401
