"""Tests for ``app/api/asset.py``."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient


def _payload(org_id: uuid.UUID, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "organization_id": str(org_id),
        "name": "web-01",
        "hostname": "web-01.internal",
        "asset_type": "virtual_machine",
        "criticality": "high",
        "tags": ["prod"],
    }
    body.update(overrides)
    return body


async def test_create_asset(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    org_id = uuid.uuid4()
    response = await client.post(
        "/inventory/assets", json=_payload(org_id), headers=auth_headers(uuid.uuid4())
    )
    assert response.status_code == 201
    body = response.json()["data"]
    assert body["name"] == "web-01"
    assert body["status"] == "discovered"
    assert set(body["tags"]) == {"prod"}


async def test_create_asset_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/inventory/assets", json=_payload(uuid.uuid4()))
    assert response.status_code == 401


async def test_create_asset_duplicate_hostname_conflicts(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    org_id = uuid.uuid4()
    headers = auth_headers(uuid.uuid4())
    first = await client.post("/inventory/assets", json=_payload(org_id), headers=headers)
    assert first.status_code == 201
    second = await client.post(
        "/inventory/assets", json=_payload(org_id, name="other"), headers=headers
    )
    assert second.status_code == 409


async def test_get_asset(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    created = await client.post("/inventory/assets", json=_payload(uuid.uuid4()), headers=headers)
    asset_id = created.json()["data"]["id"]

    response = await client.get(f"/inventory/assets/{asset_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["id"] == asset_id


async def test_get_asset_not_found(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    response = await client.get(
        f"/inventory/assets/{uuid.uuid4()}", headers=auth_headers(uuid.uuid4())
    )
    assert response.status_code == 404


async def test_list_assets_requires_auth(client: AsyncClient) -> None:
    response = await client.get(f"/inventory/assets?organization_id={uuid.uuid4()}")
    assert response.status_code == 401


async def test_list_assets(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    org_id = uuid.uuid4()
    headers = auth_headers(uuid.uuid4())
    await client.post("/inventory/assets", json=_payload(org_id), headers=headers)
    await client.post(
        "/inventory/assets", json=_payload(org_id, name="second", hostname=None), headers=headers
    )
    response = await client.get(f"/inventory/assets?organization_id={org_id}", headers=headers)
    assert response.status_code == 200
    assert len(response.json()["data"]) == 2


async def test_update_asset(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    created = await client.post("/inventory/assets", json=_payload(uuid.uuid4()), headers=headers)
    asset_id = created.json()["data"]["id"]

    update_body = {
        "name": "web-01-renamed",
        "hostname": "web-01.internal",
        "asset_type": "virtual_machine",
        "criticality": "high",
        "status": "managed",
        "health": "healthy",
        "lifecycle_state": "operational",
    }
    response = await client.put(f"/inventory/assets/{asset_id}", json=update_body, headers=headers)
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["name"] == "web-01-renamed"
    assert body["status"] == "managed"
    assert body["current_version"] == 2


async def test_patch_asset(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    created = await client.post("/inventory/assets", json=_payload(uuid.uuid4()), headers=headers)
    asset_id = created.json()["data"]["id"]

    response = await client.patch(
        f"/inventory/assets/{asset_id}", json={"health": "warning"}, headers=headers
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["health"] == "warning"
    assert body["name"] == "web-01"


async def test_delete_asset(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    created = await client.post("/inventory/assets", json=_payload(uuid.uuid4()), headers=headers)
    asset_id = created.json()["data"]["id"]

    response = await client.delete(f"/inventory/assets/{asset_id}", headers=headers)
    assert response.status_code == 200

    get_response = await client.get(f"/inventory/assets/{asset_id}", headers=headers)
    assert get_response.status_code == 404


__all__: list[str] = []
