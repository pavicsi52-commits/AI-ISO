"""Tests for ``/health``, ``/liveness``, ``/readiness``."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "healthy"
    assert body["data"]["service"]


async def test_liveness(client: AsyncClient) -> None:
    response = await client.get("/liveness")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "alive"


async def test_readiness(client: AsyncClient) -> None:
    response = await client.get("/readiness")
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "ready"
    names = {check["name"] for check in body["checks"]}
    assert {"database", "redis", "neo4j"} <= names
    for check in body["checks"]:
        assert check["status"] == "ok"


__all__: list[str] = []
