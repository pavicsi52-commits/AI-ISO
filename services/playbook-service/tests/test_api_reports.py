"""Tests for the ``/playbooks/reports`` router."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


class TestReportsApi:
    async def test_generate_repository_report(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        response = await client.get(
            "/playbooks/reports",
            params={"organization_id": str(org_id), "report_type": "repository"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["report_type"] == "repository"
        assert response.json()["data"]["result"]["total_playbooks"] == 0

    async def test_generate_validation_report_without_playbook_id_fails(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        response = await client.get(
            "/playbooks/reports",
            params={"organization_id": str(uuid.uuid4()), "report_type": "validation"},
            headers=headers,
        )
        assert response.status_code == 400

    async def test_generate_report_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get(
            "/playbooks/reports",
            params={"organization_id": str(uuid.uuid4()), "report_type": "repository"},
        )
        assert response.status_code == 401
