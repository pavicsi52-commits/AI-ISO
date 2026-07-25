"""Tests for ``/assets/{id}/assign`` and ``/assets/{id}/transfer``."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import AuthHeadersFn, make_managed_asset


async def test_assign_asset(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    managed_asset = await make_managed_asset(db_session)
    assignee_id = uuid.uuid4()

    response = await client.post(
        f"/assets/{managed_asset.id}/assign",
        json={"assignee_id": str(assignee_id), "assignment_type": "standard"},
        params={"organization_id": str(managed_asset.organization_id)},
        headers=auth_headers(uuid.uuid4()),
    )

    assert response.status_code == 201
    body = response.json()["data"]
    assert body["assignee_id"] == str(assignee_id)
    assert body["status"] == "active"


async def test_transfer_ownership(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    managed_asset = await make_managed_asset(db_session)
    principal_id = uuid.uuid4()

    response = await client.post(
        f"/assets/{managed_asset.id}/transfer",
        json={"role": "business_owner", "principal_id": str(principal_id)},
        params={"organization_id": str(managed_asset.organization_id)},
        headers=auth_headers(uuid.uuid4()),
    )

    assert response.status_code == 201
    body = response.json()["data"]
    assert body["role"] == "business_owner"
    assert body["principal_id"] == str(principal_id)
