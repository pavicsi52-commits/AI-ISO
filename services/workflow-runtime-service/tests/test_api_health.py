"""Tests for the health/liveness/readiness endpoints."""

from __future__ import annotations

from httpx import AsyncClient


class TestHealth:
    async def test_health_returns_healthy(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["status"] == "healthy"
        assert body["data"]["service"]

    async def test_liveness_returns_alive(self, client: AsyncClient) -> None:
        response = await client.get("/liveness")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "alive"

    async def test_readiness_returns_ready(self, client: AsyncClient) -> None:
        response = await client.get("/readiness")
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["status"] == "ready"
        assert any(check["name"] == "database" for check in body["data"]["checks"])
