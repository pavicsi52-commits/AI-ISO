"""HTTP-level tests for ``app/api/health.py``.

Unauthenticated by design (used by orchestrators/load balancers): no
``organization_id`` and no ``auth_headers`` on any of these requests.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import HTTP_OK


async def test_health_reports_healthy(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == HTTP_OK, response.text

    data = response.json()["data"]
    assert data["status"] == "healthy"
    assert isinstance(data["service"], str) and data["service"]
    assert isinstance(data["version"], str) and data["version"]
    assert isinstance(data["environment"], str) and data["environment"]


async def test_liveness_reports_alive(client: AsyncClient) -> None:
    response = await client.get("/liveness")
    assert response.status_code == HTTP_OK, response.text
    assert response.json()["data"]["status"] == "alive"


async def test_readiness_reports_ready_with_database_and_cache_checks(
    client: AsyncClient,
) -> None:
    response = await client.get("/readiness")
    assert response.status_code == HTTP_OK, response.text

    data = response.json()["data"]
    assert data["status"] == "ready"

    checks = data["checks"]
    assert isinstance(checks, list)
    assert len(checks) > 0
    for check in checks:
        assert isinstance(check["name"], str) and check["name"]
        assert check["status"] in ("ok", "failed")
        assert "detail" in check

    by_name = {check["name"]: check for check in checks}
    assert by_name["database"]["status"] == "ok"
    assert by_name["cache"]["status"] == "ok"


__all__: list[str] = []
