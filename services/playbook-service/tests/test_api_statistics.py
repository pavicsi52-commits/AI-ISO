"""Tests for the ``/playbooks/statistics`` router."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


class TestStatisticsApi:
    async def test_get_statistics_recomputes_when_absent(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        response = await client.get(
            "/playbooks/statistics", params={"organization_id": str(org_id)}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["data"]["total_playbooks"] == 0

    async def test_get_statistics_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get(
            "/playbooks/statistics", params={"organization_id": str(uuid.uuid4())}
        )
        assert response.status_code == 401
