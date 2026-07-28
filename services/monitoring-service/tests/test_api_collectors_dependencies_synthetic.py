"""Tests for the ``/monitoring-collectors``, ``/monitoring-dependencies``,
and ``/monitoring-synthetic-tests`` routers.
"""

from __future__ import annotations

import uuid

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


class TestMonitoringCollectorsApi:
    async def test_create_then_list(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post(
            "/monitoring-collectors",
            json={
                "organization_id": str(org_id),
                "name": "connectivity-collector",
                "collector_key": "connectivity",
                "target_types": ["physical_server"],
                "interval_seconds": 60.0,
            },
            headers=headers,
        )
        assert created.status_code == 201

        response = await client.get(
            "/monitoring-collectors", params={"organization_id": str(org_id)}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_create_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(
            "/monitoring-collectors",
            json={
                "organization_id": str(uuid.uuid4()),
                "name": "x",
                "collector_key": "dns",
            },
        )
        assert response.status_code == 401


class TestMonitoringDependenciesApi:
    async def test_create_then_list_children(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        parent_id = await _create_target(client, headers, org_id)
        child_id = await _create_target(client, headers, org_id)
        created = await client.post(
            "/monitoring-dependencies",
            json={
                "organization_id": str(org_id),
                "parent_target_id": parent_id,
                "child_target_id": child_id,
                "dependency_type": "service",
            },
            headers=headers,
        )
        assert created.status_code == 201

        response = await client.get(
            "/monitoring-dependencies", params={"parent_target_id": parent_id}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_create_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(
            "/monitoring-dependencies",
            json={
                "organization_id": str(uuid.uuid4()),
                "parent_target_id": str(uuid.uuid4()),
                "child_target_id": str(uuid.uuid4()),
                "dependency_type": "service",
            },
        )
        assert response.status_code == 401


class TestMonitoringSyntheticTestsApi:
    async def test_create_then_list(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post(
            "/monitoring-synthetic-tests",
            json={
                "organization_id": str(org_id),
                "check_type": "http",
                "name": "ping-check",
                "parameters": {"url": "http://example.internal"},
                "interval_seconds": 300.0,
            },
            headers=headers,
        )
        assert created.status_code == 201

        response = await client.get(
            "/monitoring-synthetic-tests", params={"organization_id": str(org_id)}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_create_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(
            "/monitoring-synthetic-tests",
            json={
                "organization_id": str(uuid.uuid4()),
                "check_type": "http",
                "name": "x",
            },
        )
        assert response.status_code == 401
