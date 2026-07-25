"""Tests for ``GET /assets/{id}/risk``."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_risk import AssetRisk
from app.models.enums import RiskLevel, RiskType
from tests.conftest import AuthHeadersFn, make_managed_asset


async def test_list_risk(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    managed_asset = await make_managed_asset(db_session)
    db_session.add(
        AssetRisk(
            managed_asset_id=managed_asset.id,
            organization_id=managed_asset.organization_id,
            risk_type=RiskType.SECURITY,
            level=RiskLevel.HIGH,
            score=70.0,
            evaluated_at=datetime.now(UTC),
        )
    )
    await db_session.flush()

    response = await client.get(
        f"/assets/{managed_asset.id}/risk", headers=auth_headers(uuid.uuid4())
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
    assert response.json()["data"][0]["score"] == 70.0
