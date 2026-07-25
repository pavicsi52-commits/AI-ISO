"""Tests for ``app/api/relationship.py``, ``app/api/topology.py``, and
``app/api/group.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient


async def _create_asset(
    client: AsyncClient, headers: dict[str, str], org_id: uuid.UUID, name: str
) -> str:
    response = await client.post(
        "/inventory/assets",
        json={
            "organization_id": str(org_id),
            "name": name,
            "asset_type": "application",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]  # type: ignore[no-any-return]


async def test_create_list_delete_relationship(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    org_id = uuid.uuid4()
    headers = auth_headers(uuid.uuid4())
    source_id = await _create_asset(client, headers, org_id, "source")
    target_id = await _create_asset(client, headers, org_id, "target")

    create_response = await client.post(
        "/inventory/relationships",
        json={
            "organization_id": str(org_id),
            "source_asset_id": source_id,
            "target_asset_id": target_id,
            "relationship_type": "depends_on",
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    relationship_id = create_response.json()["data"]["id"]

    list_response = await client.get(
        f"/inventory/relationships?asset_id={source_id}", headers=headers
    )
    assert list_response.status_code == 200
    assert len(list_response.json()["data"]) == 1

    delete_response = await client.delete(
        f"/inventory/relationships/{relationship_id}", headers=headers
    )
    assert delete_response.status_code == 200

    empty_response = await client.get(
        f"/inventory/relationships?asset_id={source_id}", headers=headers
    )
    assert empty_response.json()["data"] == []


async def test_relationships_require_auth(client: AsyncClient) -> None:
    response = await client.get(f"/inventory/relationships?asset_id={uuid.uuid4()}")
    assert response.status_code == 401


async def test_get_topology_neighbors_dependencies_impact(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    org_id = uuid.uuid4()
    headers = auth_headers(uuid.uuid4())
    source_id = await _create_asset(client, headers, org_id, "source")
    target_id = await _create_asset(client, headers, org_id, "target")
    await client.post(
        "/inventory/relationships",
        json={
            "organization_id": str(org_id),
            "source_asset_id": source_id,
            "target_asset_id": target_id,
            "relationship_type": "depends_on",
        },
        headers=headers,
    )

    neighbors = await client.get(
        f"/inventory/topology?asset_id={source_id}&query_kind=neighbors", headers=headers
    )
    assert neighbors.status_code == 200
    assert len(neighbors.json()["data"]["nodes"]) == 1

    dependencies = await client.get(
        f"/inventory/topology?asset_id={source_id}&query_kind=dependencies&depth=2", headers=headers
    )
    assert len(dependencies.json()["data"]["nodes"]) == 1

    impact = await client.get(
        f"/inventory/topology?asset_id={target_id}&query_kind=impact&depth=2", headers=headers
    )
    assert len(impact.json()["data"]["nodes"]) == 1


async def test_get_topology_not_found(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    response = await client.get(
        f"/inventory/topology?asset_id={uuid.uuid4()}", headers=auth_headers(uuid.uuid4())
    )
    assert response.status_code == 404


async def test_create_list_group_and_members(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    org_id = uuid.uuid4()
    headers = auth_headers(uuid.uuid4())
    asset_id = await _create_asset(client, headers, org_id, "member")

    create_response = await client.post(
        "/inventory/groups",
        json={
            "organization_id": str(org_id),
            "name": "static-group",
            "group_type": "static",
            "member_asset_ids": [asset_id],
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    group_id = create_response.json()["data"]["id"]

    list_response = await client.get(f"/inventory/groups?organization_id={org_id}", headers=headers)
    assert list_response.status_code == 200
    assert len(list_response.json()["data"]) == 1

    members_response = await client.get(f"/inventory/groups/{group_id}/members", headers=headers)
    assert members_response.status_code == 200
    assert [m["id"] for m in members_response.json()["data"]] == [asset_id]


async def test_create_group_duplicate_name_conflicts(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    org_id = uuid.uuid4()
    headers = auth_headers(uuid.uuid4())
    body = {"organization_id": str(org_id), "name": "dup-group"}
    first = await client.post("/inventory/groups", json=body, headers=headers)
    assert first.status_code == 201
    second = await client.post("/inventory/groups", json=body, headers=headers)
    assert second.status_code == 409


async def test_groups_require_auth(client: AsyncClient) -> None:
    response = await client.get(f"/inventory/groups?organization_id={uuid.uuid4()}")
    assert response.status_code == 401


__all__: list[str] = []
