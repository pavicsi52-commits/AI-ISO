"""Tests for the ``/validation/statistics`` router."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


class TestStatisticsApi:
    async def test_get_statistics_for_org_with_no_data(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        response = await client.get(
            "/validation/statistics", params={"organization_id": str(uuid.uuid4())}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["data"]["total_profiles"] == 0

    async def test_get_statistics_reflects_created_profile(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        await client.post(
            "/validations",
            json={
                "organization_id": str(org_id),
                "name": "Infra Profile",
                "profile_type": "infrastructure",
                "target_types": [],
                "check_ids": [],
            },
            headers=headers,
        )
        response = await client.get(
            "/validation/statistics", params={"organization_id": str(org_id)}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["data"]["total_profiles"] == 1

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get(
            "/validation/statistics", params={"organization_id": str(uuid.uuid4())}
        )
        assert response.status_code == 401
