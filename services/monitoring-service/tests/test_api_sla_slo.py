"""Tests for the ``/monitoring/sla`` and ``/monitoring/slo`` routers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


async def _create_target(client: AsyncClient, headers: dict[str, str], org_id: uuid.UUID) -> str:
    response = await client.post(
        "/monitoring/targets",
        json={
            "organization_id": str(org_id),
            "target_type": "physical_server",
            "external_id": f"target-{uuid.uuid4().hex[:6]}",
            "name": "Target",
        },
        headers=headers,
    )
    return str(response.json()["data"]["id"])


class TestMonitoringSlaApi:
    async def test_create_then_list(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        target_id = await _create_target(client, headers, org_id)
        now = datetime.now(UTC)
        created = await client.post(
            "/monitoring/sla",
            json={
                "organization_id": str(org_id),
                "target_id": target_id,
                "sla_type": "availability",
                "objective_percentage": 99.9,
                "period_start": (now - timedelta(days=30)).isoformat(),
                "period_end": now.isoformat(),
            },
            headers=headers,
        )
        assert created.status_code == 201

        response = await client.get(
            "/monitoring/sla", params={"organization_id": str(org_id)}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_create_requires_authentication(self, client: AsyncClient) -> None:
        now = datetime.now(UTC)
        response = await client.post(
            "/monitoring/sla",
            json={
                "organization_id": str(uuid.uuid4()),
                "target_id": str(uuid.uuid4()),
                "sla_type": "availability",
                "objective_percentage": 99.9,
                "period_start": now.isoformat(),
                "period_end": now.isoformat(),
            },
        )
        assert response.status_code == 401


class TestMonitoringSloApi:
    async def test_create_then_list(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        target_id = await _create_target(client, headers, org_id)
        now = datetime.now(UTC)
        created = await client.post(
            "/monitoring/slo",
            json={
                "organization_id": str(org_id),
                "target_id": target_id,
                "slo_type": "latency",
                "objective_value": 200.0,
                "period_start": (now - timedelta(days=30)).isoformat(),
                "period_end": now.isoformat(),
            },
            headers=headers,
        )
        assert created.status_code == 201

        response = await client.get(
            "/monitoring/slo", params={"organization_id": str(org_id)}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_create_requires_authentication(self, client: AsyncClient) -> None:
        now = datetime.now(UTC)
        response = await client.post(
            "/monitoring/slo",
            json={
                "organization_id": str(uuid.uuid4()),
                "target_id": str(uuid.uuid4()),
                "slo_type": "latency",
                "objective_value": 200.0,
                "period_start": now.isoformat(),
                "period_end": now.isoformat(),
            },
        )
        assert response.status_code == 401
