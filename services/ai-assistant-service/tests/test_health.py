"""Health/readiness/liveness endpoint tests."""

from __future__ import annotations

from httpx import AsyncClient


class TestHealth:
    async def test_health_returns_healthy(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "healthy"

    async def test_liveness_returns_alive(self, client: AsyncClient) -> None:
        response = await client.get("/liveness")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "alive"

    async def test_readiness_returns_ready(self, client: AsyncClient) -> None:
        response = await client.get("/readiness")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "ready"

    async def test_openapi_schema_available(self, client: AsyncClient) -> None:
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        assert response.json()["info"]["title"] == "AI-IOS AI Assistant Service"

    async def test_unauthenticated_business_endpoint_returns_401(self, client: AsyncClient) -> None:
        response = await client.get(
            "/ai/conversations",
            params={"organization_id": "00000000-0000-0000-0000-000000000000"},
        )
        assert response.status_code == 401
