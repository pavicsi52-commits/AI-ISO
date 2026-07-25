"""Tests for the ``/automation/templates`` router."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


def _template_body(*, organization_id: uuid.UUID | None = None) -> dict[str, object]:
    return {
        "organization_id": str(organization_id or uuid.uuid4()),
        "project_id": None,
        "template_name": "deploy-app",
        "description": "Deploys the app",
        "playbook_type": "ansible_playbook",
        "content": "- hosts: all\n  tasks: []\n",
        "variables_schema": {},
    }


class TestTemplatesRouter:
    async def test_create_template(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        response = await client.post(
            "/automation/templates", json=_template_body(), headers=auth_headers(uuid.uuid4())
        )
        assert response.status_code == 201
        assert response.json()["data"]["template_name"] == "deploy-app"

    async def test_list_templates(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        org_id = uuid.uuid4()
        headers = auth_headers(uuid.uuid4())
        await client.post(
            "/automation/templates", json=_template_body(organization_id=org_id), headers=headers
        )
        response = await client.get(
            "/automation/templates", params={"organization_id": str(org_id)}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_create_template_requires_auth(self, client: AsyncClient) -> None:
        response = await client.post("/automation/templates", json=_template_body())
        assert response.status_code == 401
