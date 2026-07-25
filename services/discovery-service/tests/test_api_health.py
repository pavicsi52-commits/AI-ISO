"""Tests for ``/health``, ``/liveness``, ``/readiness`` against the real
app lifespan (real Postgres/Redis connections).
"""

from __future__ import annotations

from httpx import AsyncClient


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "healthy"
    assert body["service"]


async def test_liveness(client: AsyncClient) -> None:
    response = await client.get("/liveness")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "alive"


async def test_readiness(client: AsyncClient) -> None:
    response = await client.get("/readiness")
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "ready"
    check_names = {check["name"] for check in body["checks"]}
    assert "database" in check_names
    assert "redis" in check_names
    assert all(check["status"] == "ok" for check in body["checks"])
