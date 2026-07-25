"""Tests for ``/assets/{id}/warranty``."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import AuthHeadersFn, make_managed_asset


async def test_get_warranty_not_found(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    managed_asset = await make_managed_asset(db_session)
    response = await client.get(
        f"/assets/{managed_asset.id}/warranty", headers=auth_headers(uuid.uuid4())
    )
    assert response.status_code == 404


async def test_update_and_get_warranty(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    managed_asset = await make_managed_asset(db_session)
    now = datetime.now(UTC)

    update_response = await client.put(
        f"/assets/{managed_asset.id}/warranty",
        json={
            "provider": "Acme Support",
            "start_date": now.isoformat(),
            "end_date": (now + timedelta(days=365)).isoformat(),
        },
        params={"organization_id": str(managed_asset.organization_id)},
        headers=auth_headers(uuid.uuid4()),
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["provider"] == "Acme Support"

    get_response = await client.get(
        f"/assets/{managed_asset.id}/warranty", headers=auth_headers(uuid.uuid4())
    )
    assert get_response.status_code == 200
    assert get_response.json()["data"]["provider"] == "Acme Support"
