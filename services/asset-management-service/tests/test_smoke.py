"""Smoke test that the conftest fixtures (Postgres, Neo4j, app) all wire up correctly."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from neo4j import AsyncDriver
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import make_managed_asset


async def test_db_session_roundtrip(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    assert managed_asset.id is not None


async def test_neo4j_connectivity(real_neo4j_driver: AsyncDriver) -> None:
    async with real_neo4j_driver.session(database="neo4j") as session:
        result = await session.run("RETURN 1 AS value")
        record = await result.single()
        assert record is not None
        assert record["value"] == 1


async def test_health_endpoint(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "healthy"


async def test_readiness_endpoint(client: AsyncClient) -> None:
    response = await client.get("/readiness")
    assert response.status_code == 200


async def test_list_managed_assets_empty(client: AsyncClient, auth_headers: object) -> None:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    headers = auth_headers(user_id)  # type: ignore[operator]
    response = await client.get("/assets", params={"organization_id": str(org_id)}, headers=headers)
    assert response.status_code == 200
    assert response.json()["data"] == []
