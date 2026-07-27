"""Tests for the ``/validation-categories``, ``/validation-checks``, and
``/validation-rules`` routers.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


class TestValidationCategoriesApi:
    async def test_create_then_list(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post(
            "/validation-categories",
            json={
                "organization_id": str(org_id),
                "name": "Security",
                "validation_type": "security",
            },
            headers=headers,
        )
        assert created.status_code == 201

        response = await client.get(
            "/validation-categories", params={"organization_id": str(org_id)}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_create_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(
            "/validation-categories",
            json={"organization_id": str(uuid.uuid4()), "name": "x", "validation_type": "custom"},
        )
        assert response.status_code == 401


class TestValidationChecksApi:
    async def test_create_then_list(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post(
            "/validation-checks",
            json={
                "organization_id": str(org_id),
                "check_type": "connectivity",
                "name": "Connectivity",
                "collector_key": "connectivity",
                "parameters": {"port": 443},
            },
            headers=headers,
        )
        assert created.status_code == 201

        response = await client.get(
            "/validation-checks", params={"organization_id": str(org_id)}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_create_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(
            "/validation-checks",
            json={
                "organization_id": str(uuid.uuid4()),
                "check_type": "cpu",
                "name": "x",
                "collector_key": "automation_job",
            },
        )
        assert response.status_code == 401


class TestValidationRulesApi:
    async def test_create_then_list(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        check = await client.post(
            "/validation-checks",
            json={
                "organization_id": str(org_id),
                "check_type": "disk_usage",
                "name": "Disk Usage",
                "collector_key": "automation_job",
                "parameters": {},
            },
            headers=headers,
        )
        check_id = check.json()["data"]["id"]

        created = await client.post(
            "/validation-rules",
            json={
                "organization_id": str(org_id),
                "check_id": check_id,
                "name": "High disk usage",
                "condition": "disk_usage_percent > 90",
            },
            headers=headers,
        )
        assert created.status_code == 201

        response = await client.get(
            "/validation-rules", params={"check_id": check_id}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_create_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(
            "/validation-rules",
            json={
                "organization_id": str(uuid.uuid4()),
                "check_id": str(uuid.uuid4()),
                "name": "x",
                "condition": "true",
            },
        )
        assert response.status_code == 401
