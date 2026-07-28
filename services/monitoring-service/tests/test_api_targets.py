"""Tests for the ``/monitoring/targets`` router."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


class TestMonitoringTargetsApi:
    async def test_create_then_list(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post(
            "/monitoring/targets",
            json={
                "organization_id": str(org_id),
                "target_type": "physical_server",
                "external_id": "server-1",
                "name": "Server One",
                "target_metadata": {"host": "10.0.0.1"},
            },
            headers=headers,
        )
        assert created.status_code == 201

        response = await client.get(
            "/monitoring/targets", params={"organization_id": str(org_id)}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_create_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(
            "/monitoring/targets",
            json={
                "organization_id": str(uuid.uuid4()),
                "target_type": "physical_server",
                "external_id": "server-2",
                "name": "Server Two",
            },
        )
        assert response.status_code == 401

    async def test_list_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get(
            "/monitoring/targets", params={"organization_id": str(uuid.uuid4())}
        )
        assert response.status_code == 401
