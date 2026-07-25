"""Tests for ``GET /assets/{id}/compliance``."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_compliance import AssetCompliance
from app.models.enums import ComplianceStatus, ComplianceType
from tests.conftest import AuthHeadersFn, make_managed_asset


async def test_list_compliance(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    managed_asset = await make_managed_asset(db_session)
    db_session.add(
        AssetCompliance(
            managed_asset_id=managed_asset.id,
            organization_id=managed_asset.organization_id,
            compliance_type=ComplianceType.SECURITY,
            status=ComplianceStatus.COMPLIANT,
            checked_at=datetime.now(UTC),
        )
    )
    await db_session.flush()

    response = await client.get(
        f"/assets/{managed_asset.id}/compliance", headers=auth_headers(uuid.uuid4())
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
