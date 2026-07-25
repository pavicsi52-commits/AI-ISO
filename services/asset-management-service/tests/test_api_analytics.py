"""Tests for ``GET /assets/analytics``."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import AuthHeadersFn, make_managed_asset


async def test_get_analytics(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    org_id = uuid.uuid4()
    await make_managed_asset(db_session, organization_id=org_id)

    response = await client.get(
        "/assets/analytics",
        params={"organization_id": str(org_id)},
        headers=auth_headers(uuid.uuid4()),
    )

    assert response.status_code == 200
    assert response.json()["data"]["total_managed_assets"] == 1
