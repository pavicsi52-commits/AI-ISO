"""Tests for ``GET /assets/{id}/dependencies``."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from neo4j import AsyncDriver
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import AuthHeadersFn, make_managed_asset, seed_dependency_graph


async def test_get_dependencies(
    client: AsyncClient,
    auth_headers: AuthHeadersFn,
    db_session: AsyncSession,
    real_neo4j_driver: AsyncDriver,
) -> None:
    source_id = uuid.uuid4()
    target_id = uuid.uuid4()
    await seed_dependency_graph(real_neo4j_driver, [(source_id, "DEPENDS_ON", target_id)])
    managed_asset = await make_managed_asset(db_session, inventory_asset_id=source_id)

    response = await client.get(
        f"/assets/{managed_asset.id}/dependencies", headers=auth_headers(uuid.uuid4())
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["inventory_asset_id"] == str(source_id)
    assert len(body["dependency_graph"]) == 1
