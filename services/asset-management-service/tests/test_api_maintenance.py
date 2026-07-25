"""Tests for ``/assets/{id}/maintenance``."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import AuthHeadersFn, make_managed_asset


async def test_schedule_and_list_maintenance(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    managed_asset = await make_managed_asset(db_session)
    scheduled_at = (datetime.now(UTC) + timedelta(days=3)).isoformat()

    create_response = await client.post(
        f"/assets/{managed_asset.id}/maintenance",
        json={
            "maintenance_type": "preventive",
            "description": "Quarterly inspection",
            "scheduled_at": scheduled_at,
        },
        params={"organization_id": str(managed_asset.organization_id)},
        headers=auth_headers(uuid.uuid4()),
    )
    assert create_response.status_code == 201
    assert create_response.json()["data"]["status"] == "scheduled"

    list_response = await client.get(
        f"/assets/{managed_asset.id}/maintenance", headers=auth_headers(uuid.uuid4())
    )
    assert list_response.status_code == 200
    assert len(list_response.json()["data"]) == 1
