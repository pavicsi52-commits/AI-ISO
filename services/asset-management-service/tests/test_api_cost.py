"""Tests for ``GET /assets/{id}/costs``."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_cost import AssetCost
from app.models.enums import CostType
from tests.conftest import AuthHeadersFn, make_managed_asset


async def test_get_costs(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    managed_asset = await make_managed_asset(db_session)
    db_session.add(
        AssetCost(
            managed_asset_id=managed_asset.id,
            organization_id=managed_asset.organization_id,
            cost_type=CostType.CLOUD,
            amount=99.5,
            currency="USD",
            incurred_at=datetime.now(UTC),
        )
    )
    await db_session.flush()

    response = await client.get(
        f"/assets/{managed_asset.id}/costs", headers=auth_headers(uuid.uuid4())
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["total_cost_of_ownership"] == 99.5
    assert len(body["entries"]) == 1
