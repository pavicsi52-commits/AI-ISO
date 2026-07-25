"""Tests for ``app/api/search.py`` -- ``GET /secrets/search``."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient


async def test_search_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/secrets/search", params={"organization_id": str(uuid.uuid4())})
    assert response.status_code == 401


async def test_search_finds_by_name(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    org_id = uuid.uuid4()
    await client.post(
        "/secrets",
        json={
            "organization_id": str(org_id),
            "name": "findable-database-password",
            "secret_type": "custom",
            "owner_id": str(caller),
            "value": "value",
        },
        headers=auth_headers(caller),
    )
    await client.post(
        "/secrets",
        json={
            "organization_id": str(org_id),
            "name": "unrelated-item",
            "secret_type": "custom",
            "owner_id": str(caller),
            "value": "value",
        },
        headers=auth_headers(caller),
    )

    response = await client.get(
        "/secrets/search",
        params={"organization_id": str(org_id), "q": "findable"},
        headers=auth_headers(caller),
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["pagination"]["total"] == 1
    assert body["items"][0]["name"] == "findable-database-password"
    assert "value" not in body["items"][0]


async def test_search_filters_by_status(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    org_id = uuid.uuid4()
    create_response = await client.post(
        "/secrets",
        json={
            "organization_id": str(org_id),
            "name": "status-filtered",
            "secret_type": "custom",
            "owner_id": str(caller),
            "value": "value",
        },
        headers=auth_headers(caller),
    )
    secret_id = create_response.json()["data"]["id"]
    await client.put(
        f"/secrets/{secret_id}",
        json={"name": "status-filtered", "status": "disabled"},
        headers=auth_headers(caller),
    )

    response = await client.get(
        "/secrets/search",
        params={"organization_id": str(org_id), "status": "disabled"},
        headers=auth_headers(caller),
    )
    assert response.status_code == 200
    assert response.json()["data"]["pagination"]["total"] == 1


async def test_search_pagination(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    org_id = uuid.uuid4()
    for i in range(3):
        await client.post(
            "/secrets",
            json={
                "organization_id": str(org_id),
                "name": f"paginated-{i}",
                "secret_type": "custom",
                "owner_id": str(caller),
                "value": "value",
            },
            headers=auth_headers(caller),
        )

    response = await client.get(
        "/secrets/search",
        params={"organization_id": str(org_id), "page": 1, "page_size": 2},
        headers=auth_headers(caller),
    )
    body = response.json()["data"]
    assert len(body["items"]) == 2
    assert body["pagination"]["total"] == 3
    assert body["pagination"]["has_next"] is True
