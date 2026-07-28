"""Tests for the ``/monitoring/thresholds`` and ``/monitoring-rules`` routers."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


async def _create_metric(client: AsyncClient, headers: dict[str, str], org_id: uuid.UUID) -> str:
    response = await client.post(
        "/monitoring/metrics",
        json={
            "organization_id": str(org_id),
            "metric_type": "cpu_usage",
            "name": "cpu_usage_percent",
        },
        headers=headers,
    )
    return str(response.json()["data"]["id"])


class TestMonitoringThresholdsApi:
    async def test_create_then_list(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        metric_id = await _create_metric(client, headers, org_id)
        created = await client.post(
            "/monitoring/thresholds",
            json={
                "organization_id": str(org_id),
                "metric_id": metric_id,
                "high": 80.0,
                "critical": 95.0,
            },
            headers=headers,
        )
        assert created.status_code == 201

        response = await client.get(
            "/monitoring/thresholds", params={"metric_id": metric_id}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_create_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(
            "/monitoring/thresholds",
            json={"organization_id": str(uuid.uuid4()), "metric_id": str(uuid.uuid4())},
        )
        assert response.status_code == 401


class TestMonitoringRulesApi:
    async def test_create_then_list(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        metric_id = await _create_metric(client, headers, org_id)
        created = await client.post(
            "/monitoring-rules",
            json={
                "organization_id": str(org_id),
                "metric_id": metric_id,
                "rule_type": "metric",
                "name": "cpu-spike",
                "condition": "value > 90",
            },
            headers=headers,
        )
        assert created.status_code == 201

        response = await client.get(
            "/monitoring-rules", params={"organization_id": str(org_id)}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_create_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(
            "/monitoring-rules",
            json={
                "organization_id": str(uuid.uuid4()),
                "rule_type": "metric",
                "name": "x",
                "condition": "true",
            },
        )
        assert response.status_code == 401
