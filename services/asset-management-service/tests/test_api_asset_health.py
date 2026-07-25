"""Tests for ``GET /assets/{id}/health``."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_health_rollup import AssetHealthRollup
from tests.conftest import AuthHeadersFn, make_managed_asset


async def test_get_health_rollup_not_found(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    managed_asset = await make_managed_asset(db_session)
    response = await client.get(
        f"/assets/{managed_asset.id}/health", headers=auth_headers(uuid.uuid4())
    )
    assert response.status_code == 404


async def test_get_health_rollup(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    managed_asset = await make_managed_asset(db_session)
    db_session.add(
        AssetHealthRollup(
            managed_asset_id=managed_asset.id,
            organization_id=managed_asset.organization_id,
            health_score=88.0,
            computed_at=datetime.now(UTC),
        )
    )
    await db_session.flush()

    response = await client.get(
        f"/assets/{managed_asset.id}/health", headers=auth_headers(uuid.uuid4())
    )
    assert response.status_code == 200
    assert response.json()["data"]["health_score"] == 88.0
