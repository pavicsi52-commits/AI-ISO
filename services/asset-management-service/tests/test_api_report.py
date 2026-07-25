"""Tests for ``GET /assets/reports``."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import AuthHeadersFn, make_managed_asset


async def test_generate_report(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    managed_asset = await make_managed_asset(db_session)

    response = await client.get(
        "/assets/reports",
        params={
            "organization_id": str(managed_asset.organization_id),
            "report_type": "asset",
            "managed_asset_id": str(managed_asset.id),
        },
        headers=auth_headers(uuid.uuid4()),
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["report_type"] == "asset"
    assert body["result"]["business_name"] == managed_asset.business_name


async def test_generate_executive_dashboard_report(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    org_id = uuid.uuid4()
    await make_managed_asset(db_session, organization_id=org_id)

    response = await client.get(
        "/assets/reports",
        params={"organization_id": str(org_id), "report_type": "executive_dashboard"},
        headers=auth_headers(uuid.uuid4()),
    )

    assert response.status_code == 200
    assert response.json()["data"]["result"]["total_managed_assets"] == 1
