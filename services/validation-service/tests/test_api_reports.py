"""Tests for the ``/validation/reports`` router."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


class TestReportsApi:
    async def test_generate_executive_report(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        response = await client.get(
            "/validation/reports",
            params={"organization_id": str(uuid.uuid4()), "report_type": "executive"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["report_type"] == "executive"

    async def test_generate_validation_report_without_execution_id_returns_400(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        response = await client.get(
            "/validation/reports",
            params={"organization_id": str(uuid.uuid4()), "report_type": "validation"},
            headers=headers,
        )
        assert response.status_code == 400

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get(
            "/validation/reports",
            params={"organization_id": str(uuid.uuid4()), "report_type": "executive"},
        )
        assert response.status_code == 401
