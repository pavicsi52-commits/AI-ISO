"""Tests for ``/discovery/profiles`` against the real app lifespan."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient


async def test_create_list_update_delete_profile(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    org_id = uuid.uuid4()

    create_resp = await client.post(
        "/discovery/profiles",
        json={
            "organization_id": str(org_id),
            "name": f"api-profile-{uuid.uuid4()}",
            "profile_type": "custom",
            "protocols": ["tcp", "icmp"],
            "timeout_seconds": 15,
            "concurrency_limit": 3,
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    profile = create_resp.json()["data"]
    assert profile["protocols"] == ["tcp", "icmp"]
    assert profile["is_system"] is False
    profile_id = profile["id"]

    list_resp = await client.get(
        "/discovery/profiles", params={"organization_id": str(org_id)}, headers=headers
    )
    assert list_resp.status_code == 200
    assert any(item["id"] == profile_id for item in list_resp.json()["data"])

    update_resp = await client.put(
        f"/discovery/profiles/{profile_id}",
        json={
            "name": "renamed-profile",
            "profile_type": "deep_scan",
            "protocols": ["ssh"],
            "timeout_seconds": 45,
            "concurrency_limit": 8,
        },
        headers=headers,
    )
    assert update_resp.status_code == 200, update_resp.text
    updated = update_resp.json()["data"]
    assert updated["name"] == "renamed-profile"
    assert updated["profile_type"] == "deep_scan"
    assert updated["timeout_seconds"] == 45

    delete_resp = await client.delete(f"/discovery/profiles/{profile_id}", headers=headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["data"]["success"] is True


async def test_create_duplicate_name_returns_conflict(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    org_id = uuid.uuid4()
    body = {
        "organization_id": str(org_id),
        "name": "dup-profile",
        "profile_type": "custom",
        "protocols": [],
    }
    first = await client.post("/discovery/profiles", json=body, headers=headers)
    assert first.status_code == 201
    second = await client.post("/discovery/profiles", json=body, headers=headers)
    assert second.status_code == 409


async def test_update_unknown_profile_returns_404(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    response = await client.put(
        f"/discovery/profiles/{uuid.uuid4()}",
        json={"name": "x", "profile_type": "custom", "protocols": []},
        headers=headers,
    )
    assert response.status_code == 404


async def test_profile_endpoints_require_authentication(client: AsyncClient) -> None:
    response = await client.get(
        "/discovery/profiles", params={"organization_id": str(uuid.uuid4())}
    )
    assert response.status_code == 401
