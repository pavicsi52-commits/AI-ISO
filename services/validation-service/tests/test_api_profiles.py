"""Tests for the ``/validation-profiles`` router."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


class TestValidationProfilesApi:
    async def test_create_then_list(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post(
            "/validation-profiles",
            json={
                "organization_id": str(org_id),
                "name": "Security Profile",
                "profile_type": "security",
                "target_types": [],
                "check_ids": [],
            },
            headers=headers,
        )
        assert created.status_code == 201

        response = await client.get(
            "/validation-profiles", params={"organization_id": str(org_id)}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_create_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(
            "/validation-profiles",
            json={
                "organization_id": str(uuid.uuid4()),
                "name": "x",
                "profile_type": "custom",
                "target_types": [],
                "check_ids": [],
            },
        )
        assert response.status_code == 401
