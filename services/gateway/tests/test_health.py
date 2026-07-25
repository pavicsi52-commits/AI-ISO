"""Tests for the health, readiness, liveness, and metrics endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_healthy_status(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "healthy"
    assert body["data"]["service"] == "gateway"
    assert "request_id" in body["meta"]


def test_liveness_returns_alive(client: TestClient) -> None:
    response = client.get("/liveness")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "alive"


def test_readiness_returns_ready(client: TestClient) -> None:
    response = client.get("/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "ready"
    assert body["data"]["checks"][0]["name"] == "configuration"
    assert body["data"]["checks"][0]["status"] == "ok"


def test_metrics_endpoint_exposes_prometheus_format(client: TestClient) -> None:
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]


def test_response_includes_request_id_headers(client: TestClient) -> None:
    response = client.get("/health")

    assert "x-request-id" in response.headers
    assert "x-correlation-id" in response.headers


def test_request_id_header_is_honored_when_supplied(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "test-request-id"})

    assert response.headers["x-request-id"] == "test-request-id"


def test_unknown_route_returns_standard_error_envelope(client: TestClient) -> None:
    response = client.get("/does-not-exist")

    assert response.status_code == 404


def test_openapi_schema_is_available(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "AI-IOS Gateway"
    assert "/health" in schema["paths"]
