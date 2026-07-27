"""Tests for the ``/health``/``/readiness``/``/liveness`` endpoints."""

from __future__ import annotations

from httpx import AsyncClient


class TestHealthApi:
    async def test_health(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "healthy"

    async def test_liveness(self, client: AsyncClient) -> None:
        response = await client.get("/liveness")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "alive"

    async def test_readiness(self, client: AsyncClient) -> None:
        response = await client.get("/readiness")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "ready"
        assert data["checks"][0]["name"] == "database"
