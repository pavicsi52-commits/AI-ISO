"""HTTP tests for /health, /liveness, /readiness.

None of these routes take ``organization_id`` or need ``Authorization``
headers -- the one exception to every other router in this service.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from tests.conftest import HTTP_OK

pytestmark = pytest.mark.asyncio


class TestHealth:
    async def test_health_reports_healthy(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.status_code == HTTP_OK
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["status"] == "healthy"
        assert data["service"]
        assert data["version"]
        assert data["environment"]


class TestLiveness:
    async def test_liveness_reports_alive(self, client: AsyncClient) -> None:
        resp = await client.get("/liveness")
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["status"] == "alive"


class TestReadiness:
    async def test_readiness_reports_ready_with_a_database_check(self, client: AsyncClient) -> None:
        resp = await client.get("/readiness")
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["status"] == "ready"
        checks_by_name = {check["name"]: check for check in data["checks"]}
        assert checks_by_name["database"]["status"] == "ok"
        assert checks_by_name["cache"]["status"] == "ok"

    async def test_readiness_reports_a_failed_cache_check_when_redis_is_unreachable(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        class _BrokenRedis:
            async def ping(self) -> None:
                raise ConnectionError("Simulated redis outage.")

        original = app.state.redis_client
        app.state.redis_client = _BrokenRedis()
        try:
            resp = await client.get("/readiness")
        finally:
            app.state.redis_client = original
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        # Redis backs only the sweeps' own leader election -- losing it
        # makes readiness report the failure without gating overall
        # status, since PostgreSQL alone is what actually gates traffic.
        assert data["status"] == "ready"
        checks_by_name = {check["name"]: check for check in data["checks"]}
        assert checks_by_name["cache"]["status"] == "failed"

    async def test_readiness_omits_the_cache_check_when_no_redis_client_is_configured(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        original = app.state.redis_client
        app.state.redis_client = None
        try:
            resp = await client.get("/readiness")
        finally:
            app.state.redis_client = original
        assert resp.status_code == HTTP_OK
        checks_by_name = {check["name"]: check for check in resp.json()["data"]["checks"]}
        assert "cache" not in checks_by_name
