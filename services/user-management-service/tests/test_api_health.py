"""Tests for GET /health, /liveness, /readiness."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health_reports_healthy(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "healthy"


async def test_liveness_reports_alive(client: AsyncClient) -> None:
    response = await client.get("/liveness")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "alive"


async def test_readiness_reports_ready(client: AsyncClient) -> None:
    response = await client.get("/readiness")

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "ready"
    names = {check["name"] for check in body["checks"]}
    assert {"database", "redis"} <= names


async def test_openapi_schema_is_served(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "AI-IOS User Management Service"
