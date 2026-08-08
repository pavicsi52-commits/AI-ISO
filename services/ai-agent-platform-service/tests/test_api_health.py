"""Edge-case and structural coverage for ``app/api/health.py``.

``tests/test_smoke.py`` already confirms the golden path (``/health``,
``/readiness``, ``/liveness`` all succeed once). This file covers the
response *shape* readiness must always have regardless of which
dependency happens to be reachable in this environment, plus the two
private per-dependency check helpers' own fault-tolerant branches --
exercised directly as plain async functions (no FastAPI routing or DI
involved) since a real Redis/Neo4j outage cannot be reliably forced
from a test.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient

from app.api.health import _cache_check, _graph_check
from tests.conftest import HTTP_OK

_READINESS_CHECK_NAMES = {"database", "cache", "graph"}
_READINESS_STATUSES = {"ok", "failed"}


async def test_health_endpoint_shape(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == HTTP_OK
    body = response.json()

    assert body["success"] is True
    assert isinstance(body["message"], str) and body["message"]
    assert set(body["meta"].keys()) == {"request_id", "timestamp"}
    assert isinstance(body["meta"]["request_id"], str)

    data = body["data"]
    assert data["status"] == "healthy"
    assert isinstance(data["service"], str) and data["service"]
    assert isinstance(data["version"], str) and data["version"]
    assert isinstance(data["environment"], str) and data["environment"]


async def test_health_does_not_require_authentication(client: AsyncClient) -> None:
    # No Authorization header at all -- /health has no CurrentUserId
    # dependency, so this must never 401.
    response = await client.get("/health")
    assert response.status_code == HTTP_OK


async def test_liveness_endpoint_shape(client: AsyncClient) -> None:
    response = await client.get("/liveness")
    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["success"] is True
    assert body["data"] == {"status": "alive"}


async def test_readiness_endpoint_shape(client: AsyncClient) -> None:
    response = await client.get("/readiness")
    assert response.status_code == HTTP_OK
    body = response.json()

    assert body["success"] is True
    data = body["data"]
    assert data["status"] in {"ready", "not_ready"}

    checks = data["checks"]
    assert isinstance(checks, list)
    assert len(checks) >= 1

    names = [check["name"] for check in checks]
    assert "database" in names
    # Every check this app can report is one of database/cache/graph --
    # never an unexpected fourth name.
    assert set(names) <= _READINESS_CHECK_NAMES
    # No duplicate dependency reported twice.
    assert len(names) == len(set(names))

    for check in checks:
        assert set(check.keys()) == {"name", "status", "detail"}
        assert check["status"] in _READINESS_STATUSES
        assert check["detail"] is None or isinstance(check["detail"], str)

    database_check = next(check for check in checks if check["name"] == "database")
    # The database check's own detail is always the measured latency,
    # regardless of whether it came back healthy or not.
    assert database_check["detail"] is not None
    assert database_check["detail"].endswith("ms")


async def test_readiness_overall_status_reflects_database_only(client: AsyncClient) -> None:
    """Per this module's own docstring, only the database check gates
    the overall ``ready``/``not_ready`` verdict -- cache and graph never
    do. Confirm the two never disagree."""
    response = await client.get("/readiness")
    body = response.json()
    data = body["data"]

    database_check = next(check for check in data["checks"] if check["name"] == "database")
    if database_check["status"] == "ok":
        assert data["status"] == "ready"
    else:
        assert data["status"] == "not_ready"


async def test_readiness_does_not_require_authentication(client: AsyncClient) -> None:
    response = await client.get("/readiness")
    assert response.status_code == HTTP_OK


async def test_readiness_skips_cache_check_when_redis_client_unset(
    client: AsyncClient, app: FastAPI
) -> None:
    """``readiness``'s own ``if redis_client is not None`` guard covers a
    deployment where ``app.state`` never got a ``redis_client`` at all
    (as opposed to one that is present but unreachable, which
    ``_cache_check``'s own failure branch above already covers).
    Temporarily removing the real app's own attribute -- restored in a
    ``finally`` -- is the only way to exercise that branch, since the
    real lifespan this suite boots through always sets it."""
    original = app.state.redis_client
    del app.state.redis_client
    try:
        response = await client.get("/readiness")
        assert response.status_code == HTTP_OK
        names = [check["name"] for check in response.json()["data"]["checks"]]
        assert "cache" not in names
        assert "database" in names
        assert "graph" in names
    finally:
        app.state.redis_client = original


# ---- direct unit coverage of the two private per-dependency checks --------
#
# These call the module's own private helpers directly with a
# duck-typed stand-in for the one collaborator each takes (a Redis
# client / the graph client on ``request.app.state``) -- not mocking
# FastAPI's routing or dependency injection, just forcing the
# success/failure branch a live environment cannot guarantee.


class _OkRedis:
    async def ping(self) -> bool:
        return True


class _FailingRedis:
    async def ping(self) -> None:
        raise ConnectionError("connection refused")


async def test_cache_check_ok_branch() -> None:
    result = await _cache_check(_OkRedis())  # type: ignore[arg-type]
    assert result.name == "cache"
    assert result.status == "ok"
    assert result.detail == "redis responded to ping"


async def test_cache_check_swallows_failure_into_failed_status() -> None:
    result = await _cache_check(_FailingRedis())  # type: ignore[arg-type]
    assert result.name == "cache"
    assert result.status == "failed"
    assert result.detail is not None
    assert "redis is unreachable" in result.detail
    assert "connection refused" in result.detail


class _FakeGraphClient:
    def __init__(self, *, enabled: bool, verified: bool) -> None:
        self.enabled = enabled
        self._verified = verified

    async def verify(self) -> bool:
        return self._verified


class _FakeAppState:
    def __init__(self, graph_client: Any) -> None:
        self.graph_client = graph_client


class _FakeApp:
    def __init__(self, graph_client: Any) -> None:
        self.state = _FakeAppState(graph_client)


class _FakeRequest:
    def __init__(self, graph_client: Any) -> None:
        self.app = _FakeApp(graph_client)


async def test_graph_check_not_configured_when_client_missing() -> None:
    result = await _graph_check(_FakeRequest(None))  # type: ignore[arg-type]
    assert result.name == "graph"
    assert result.status == "ok"
    assert result.detail == "not configured on this deployment"


async def test_graph_check_not_configured_when_disabled() -> None:
    fake_client = _FakeGraphClient(enabled=False, verified=True)
    result = await _graph_check(_FakeRequest(fake_client))  # type: ignore[arg-type]
    assert result.status == "ok"
    assert result.detail == "not configured on this deployment"


async def test_graph_check_ok_when_enabled_and_verified() -> None:
    fake_client = _FakeGraphClient(enabled=True, verified=True)
    result = await _graph_check(_FakeRequest(fake_client))  # type: ignore[arg-type]
    assert result.status == "ok"
    assert result.detail == "neo4j responded"


async def test_graph_check_failed_when_enabled_but_not_verified() -> None:
    fake_client = _FakeGraphClient(enabled=True, verified=False)
    result = await _graph_check(_FakeRequest(fake_client))  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.detail == "neo4j did not respond"
