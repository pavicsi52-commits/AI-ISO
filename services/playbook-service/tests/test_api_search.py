"""Tests for the ``/playbooks/search`` router."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


class TestSearchApi:
    async def test_search_finds_created_playbook(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        await client.post(
            "/playbooks",
            json={
                "organization_id": str(org_id),
                "name": "searchable-playbook",
                "content_type": "shell_script",
                "initial_content": "echo hi",
            },
            headers=headers,
        )

        response = await client.get(
            "/playbooks/search",
            params={"organization_id": str(org_id), "query": "searchable"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["data"][0]["name"] == "searchable-playbook"

    async def test_search_filters_by_status(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        await client.post(
            "/playbooks",
            json={
                "organization_id": str(org_id),
                "name": "draft-playbook",
                "content_type": "shell_script",
                "initial_content": "echo hi",
            },
            headers=headers,
        )

        response = await client.get(
            "/playbooks/search",
            params={"organization_id": str(org_id), "status": "published"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_search_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get(
            "/playbooks/search", params={"organization_id": str(uuid.uuid4())}
        )
        assert response.status_code == 401
