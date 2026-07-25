"""Tests for ``GET /readiness``'s Neo4j dependency-check branch --
``app/api/health.py`` -- against a driver forced to fail connectivity.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.factory import create_app


class _BrokenNeo4jDriver:
    async def verify_connectivity(self) -> None:
        raise RuntimeError("connection refused")

    async def close(self) -> None:
        """No-op -- ``_lifespan``'s shutdown path calls this on whatever
        driver ``app.state.neo4j_driver`` holds at teardown time.
        """


@pytest.fixture
async def app_with_broken_neo4j(db_session: AsyncSession) -> AsyncIterator[FastAPI]:
    application = create_app()
    async with application.router.lifespan_context(application):

        async def _override_db_session() -> AsyncIterator[AsyncSession]:
            yield db_session

        application.dependency_overrides[deps.get_db_session] = _override_db_session
        # ``app/api/health.py``'s readiness check reads
        # ``request.app.state.neo4j_driver`` directly (not through a
        # ``Depends``-injected parameter), so ``dependency_overrides``
        # has no effect here -- the state attribute itself must be
        # replaced after lifespan startup has already set the real one.
        # The real driver lifespan just opened is closed immediately
        # since nothing else in this test needs it.
        await application.state.neo4j_driver.close()
        application.state.neo4j_driver = _BrokenNeo4jDriver()
        yield application


async def test_readiness_reports_not_ready_when_neo4j_unreachable(
    app_with_broken_neo4j: FastAPI,
) -> None:
    transport = ASGITransport(app=app_with_broken_neo4j)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/readiness")

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "not_ready"
    neo4j_check = next(check for check in body["checks"] if check["name"] == "neo4j")
    assert neo4j_check["status"] == "failed"
