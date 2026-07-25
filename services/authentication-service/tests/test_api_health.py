"""Tests for GET /health, /liveness, /readiness."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health_reports_healthy(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "healthy"
    assert body["data"]["service"]


async def test_liveness_reports_alive(client: AsyncClient) -> None:
    response = await client.get("/liveness")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "alive"


async def test_readiness_reports_ready_with_real_checks(client: AsyncClient) -> None:
    response = await client.get("/readiness")

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "ready"
    names = {check["name"] for check in body["checks"]}
    assert {"database", "redis"} <= names
    assert all(check["status"] == "ok" for check in body["checks"])


async def test_openapi_schema_is_served(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "AI-IOS Authentication Service"


async def test_metrics_endpoint_exposes_prometheus_text(client: AsyncClient) -> None:
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert b"python_gc_objects_collected_total" in response.content
