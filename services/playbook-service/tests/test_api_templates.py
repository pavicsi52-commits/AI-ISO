"""Tests for the ``/playbooks/templates`` router."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


class TestTemplatesApi:
    async def test_create_then_list_templates(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        create_response = await client.post(
            "/playbooks/templates",
            json={
                "organization_id": str(org_id),
                "template_name": "deploy-tpl",
                "content_type": "shell_script",
                "content": "echo hi",
            },
            headers=headers,
        )
        assert create_response.status_code == 201
        assert create_response.json()["data"]["template_name"] == "deploy-tpl"

        list_response = await client.get(
            "/playbooks/templates", params={"organization_id": str(org_id)}, headers=headers
        )
        assert list_response.status_code == 200
        assert len(list_response.json()["data"]) == 1

    async def test_list_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get(
            "/playbooks/templates", params={"organization_id": str(uuid.uuid4())}
        )
        assert response.status_code == 401
