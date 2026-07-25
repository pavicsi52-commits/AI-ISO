"""Tests for ``/assets`` -- ``app/api/managed_asset.py``."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from pytest_httpx import HTTPXMock
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import INVENTORY_SERVICE_BASE_URL, AuthHeadersFn, make_managed_asset


def _inventory_url(inventory_asset_id: uuid.UUID) -> str:
    return f"{INVENTORY_SERVICE_BASE_URL}/inventory/assets/{inventory_asset_id}"


async def test_create_managed_asset(
    client: AsyncClient, auth_headers: AuthHeadersFn, httpx_mock: HTTPXMock
) -> None:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    inventory_asset_id = uuid.uuid4()
    httpx_mock.add_response(
        method="GET",
        url=_inventory_url(inventory_asset_id),
        json={"data": {"id": str(inventory_asset_id), "name": "web-01"}},
    )

    response = await client.post(
        "/assets",
        json={
            "organization_id": str(org_id),
            "inventory_asset_id": str(inventory_asset_id),
            "business_name": "Payments API",
            "criticality": "high",
        },
        headers=auth_headers(user_id),
    )

    assert response.status_code == 201
    body = response.json()["data"]
    assert body["business_name"] == "Payments API"
    assert body["status"] == "planned"


async def test_create_managed_asset_missing_inventory_asset_returns_404(
    client: AsyncClient, auth_headers: AuthHeadersFn, httpx_mock: HTTPXMock
) -> None:
    org_id = uuid.uuid4()
    inventory_asset_id = uuid.uuid4()
    httpx_mock.add_response(method="GET", url=_inventory_url(inventory_asset_id), status_code=404)

    response = await client.post(
        "/assets",
        json={
            "organization_id": str(org_id),
            "inventory_asset_id": str(inventory_asset_id),
            "business_name": "Ghost Asset",
        },
        headers=auth_headers(uuid.uuid4()),
    )

    assert response.status_code == 404


async def test_get_managed_asset(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    managed_asset = await make_managed_asset(db_session)
    response = await client.get(f"/assets/{managed_asset.id}", headers=auth_headers(uuid.uuid4()))
    assert response.status_code == 200
    assert response.json()["data"]["id"] == str(managed_asset.id)


async def test_get_managed_asset_not_found(
    client: AsyncClient, auth_headers: AuthHeadersFn
) -> None:
    response = await client.get(f"/assets/{uuid.uuid4()}", headers=auth_headers(uuid.uuid4()))
    assert response.status_code == 404


async def test_list_managed_assets(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    org_id = uuid.uuid4()
    await make_managed_asset(db_session, organization_id=org_id)
    await make_managed_asset(db_session, organization_id=org_id)

    response = await client.get(
        "/assets", params={"organization_id": str(org_id)}, headers=auth_headers(uuid.uuid4())
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 2


async def test_update_managed_asset(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    managed_asset = await make_managed_asset(db_session)

    response = await client.put(
        f"/assets/{managed_asset.id}",
        json={
            "business_name": "Renamed Asset",
            "status": "operational",
            "lifecycle_state": "operational",
            "criticality": "high",
        },
        headers=auth_headers(uuid.uuid4()),
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["business_name"] == "Renamed Asset"
    assert body["status"] == "operational"


async def test_patch_managed_asset(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    managed_asset = await make_managed_asset(db_session)

    response = await client.patch(
        f"/assets/{managed_asset.id}",
        json={"business_name": "Patched Name"},
        headers=auth_headers(uuid.uuid4()),
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["business_name"] == "Patched Name"
    assert body["status"] == managed_asset.status.value


async def test_delete_managed_asset(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    managed_asset = await make_managed_asset(db_session)

    response = await client.delete(
        f"/assets/{managed_asset.id}", headers=auth_headers(uuid.uuid4())
    )
    assert response.status_code == 200
    assert response.json()["data"]["success"] is True

    follow_up = await client.get(f"/assets/{managed_asset.id}", headers=auth_headers(uuid.uuid4()))
    assert follow_up.status_code == 404


async def test_endpoints_require_authentication(client: AsyncClient) -> None:
    response = await client.get("/assets", params={"organization_id": str(uuid.uuid4())})
    assert response.status_code == 401
