"""Tests for the ``/validation-templates`` router."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


class TestValidationTemplatesApi:
    async def test_create_then_list(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post(
            "/validation-templates",
            json={
                "organization_id": str(org_id),
                "name": "Baseline Health",
                "profile_type": "health",
                "template_content": {"check_ids": []},
            },
            headers=headers,
        )
        assert created.status_code == 201

        response = await client.get(
            "/validation-templates", params={"organization_id": str(org_id)}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_create_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(
            "/validation-templates",
            json={
                "organization_id": str(uuid.uuid4()),
                "name": "x",
                "profile_type": "custom",
                "template_content": {},
            },
        )
        assert response.status_code == 401
