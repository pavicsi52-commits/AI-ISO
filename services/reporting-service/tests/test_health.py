"""Health, readiness, liveness, metrics, and OpenAPI."""

from __future__ import annotations

from httpx import AsyncClient


class TestHealthEndpoints:
    async def test_health_is_served(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "healthy"

    async def test_liveness_is_served(self, client: AsyncClient) -> None:
        assert (await client.get("/liveness")).status_code == 200

    async def test_readiness_checks_the_real_database(self, client: AsyncClient) -> None:
        response = await client.get("/readiness")
        assert response.status_code == 200
        checks = response.json()["data"]["checks"]
        assert any(check["name"] == "database" and check["status"] == "ok" for check in checks)

    async def test_metrics_are_exposed(self, client: AsyncClient) -> None:
        response = await client.get("/metrics")
        assert response.status_code == 200
        assert "# HELP" in response.text

    async def test_openapi_documents_every_route(self, client: AsyncClient) -> None:
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        paths = response.json()["paths"]
        assert "/reports" in paths
        assert "/reports/generate" in paths
        assert "/reports/templates" in paths
        assert "/reports/archive" in paths

    async def test_every_operation_is_documented(self, client: AsyncClient) -> None:
        """Generated docs are only useful if every operation describes itself."""
        schema = (await client.get("/openapi.json")).json()
        for path, operations in schema["paths"].items():
            for method, operation in operations.items():
                assert operation.get("summary"), f"{method.upper()} {path} has no summary"
                assert operation.get("description"), f"{method.upper()} {path} has no description"
