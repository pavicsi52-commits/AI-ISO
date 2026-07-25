"""Tests for ``/assets/{id}/contracts``."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import AuthHeadersFn, make_managed_asset


async def test_create_and_list_contracts(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    managed_asset = await make_managed_asset(db_session)
    now = datetime.now(UTC)

    create_response = await client.post(
        f"/assets/{managed_asset.id}/contracts",
        json={
            "contract_type": "support",
            "start_date": now.isoformat(),
            "end_date": (now + timedelta(days=365)).isoformat(),
        },
        params={"organization_id": str(managed_asset.organization_id)},
        headers=auth_headers(uuid.uuid4()),
    )
    assert create_response.status_code == 201
    assert create_response.json()["data"]["contract_type"] == "support"

    list_response = await client.get(
        f"/assets/{managed_asset.id}/contracts", headers=auth_headers(uuid.uuid4())
    )
    assert list_response.status_code == 200
    assert len(list_response.json()["data"]) == 1
