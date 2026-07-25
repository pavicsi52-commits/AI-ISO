"""Tests for ``app/api/health.py``."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "healthy"


async def test_liveness(client: AsyncClient) -> None:
    response = await client.get("/liveness")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "alive"


async def test_readiness(client: AsyncClient) -> None:
    response = await client.get("/readiness")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "ready"
    check_names = {check["name"] for check in body["data"]["checks"]}
    assert {"database", "redis"} <= check_names
