"""Tests for ``app/api/api_key.py``."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient


async def test_create_api_key_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/api-keys",
        json={
            "organization_id": str(uuid.uuid4()),
            "name": "no-auth",
            "owner_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 401


async def test_create_and_list_api_key(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    org_id = uuid.uuid4()

    create_response = await client.post(
        "/api-keys",
        json={
            "organization_id": str(org_id),
            "name": "openai-key",
            "owner_id": str(caller),
            "scopes": ["chat"],
        },
        headers=auth_headers(caller),
    )
    assert create_response.status_code == 201
    body = create_response.json()["data"]
    assert body["value"].startswith("aiios_")
    assert body["key_prefix"] == body["value"][:12]

    list_response = await client.get(
        "/api-keys", params={"organization_id": str(org_id)}, headers=auth_headers(caller)
    )
    assert list_response.status_code == 200
    for item in list_response.json()["data"]:
        assert "value" not in item


async def test_delete_api_key(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    create_response = await client.post(
        "/api-keys",
        json={
            "organization_id": str(uuid.uuid4()),
            "name": "deletable",
            "owner_id": str(caller),
        },
        headers=auth_headers(caller),
    )
    api_key_id = create_response.json()["data"]["id"]

    delete_response = await client.delete(f"/api-keys/{api_key_id}", headers=auth_headers(caller))
    assert delete_response.status_code == 200
