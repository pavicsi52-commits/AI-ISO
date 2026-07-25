"""HTTP-level tests for the ``/users`` CRUD/search surface."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from httpx import AsyncClient


async def _create_user(
    client: AsyncClient, headers: dict[str, str], **overrides: Any
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "username": f"user-{uuid.uuid4().hex[:12]}",
        "email": f"user-{uuid.uuid4().hex}@example.com",
        "display_name": "Test User",
    }
    body.update(overrides)
    response = await client.post("/users", headers=headers, json=body)
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()["data"]
    return data


async def test_create_user_returns_201(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())

    data = await _create_user(client, headers)

    assert data["status"] == "pending"


async def test_create_user_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        "/users", json={"username": "nouser", "email": "nouser@example.com"}
    )

    assert response.status_code == 401


async def test_create_user_rejects_duplicate_username(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    created = await _create_user(client, headers)

    response = await client.post(
        "/users",
        headers=headers,
        json={
            "username": created["username"],
            "email": f"other-{uuid.uuid4().hex}@example.com",
        },
    )

    assert response.status_code == 409


async def test_get_user_returns_detail(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    created = await _create_user(client, headers)

    response = await client.get(f"/users/{created['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["username"] == created["username"]


async def test_get_user_is_cached_on_second_call(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    created = await _create_user(client, headers)

    first = await client.get(f"/users/{created['id']}", headers=headers)
    second = await client.get(f"/users/{created['id']}", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"] == second.json()["data"]


async def test_get_unknown_user_returns_404(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())

    response = await client.get(f"/users/{uuid.uuid4()}", headers=headers)

    assert response.status_code == 404


async def test_list_users(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    await _create_user(client, headers)

    response = await client.get("/users", headers=headers)

    assert response.status_code == 200
    assert len(response.json()["data"]) >= 1


async def test_search_users_by_query(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    created = await _create_user(client, headers)

    response = await client.post(
        "/users/search", headers=headers, json={"query": created["username"]}
    )

    assert response.status_code == 200
    assert any(u["id"] == created["id"] for u in response.json()["data"])


async def test_search_users_by_status_filter(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    created = await _create_user(client, headers)

    response = await client.post("/users/search", headers=headers, json={"status": "pending"})

    assert response.status_code == 200
    assert any(u["id"] == created["id"] for u in response.json()["data"])


async def test_replace_user(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    created = await _create_user(client, headers)

    response = await client.put(
        f"/users/{created['id']}",
        headers=headers,
        json={"display_name": "Replaced", "timezone": "UTC", "language": "en", "locale": "en-US"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["display_name"] == "Replaced"


async def test_patch_user_status_transition(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    created = await _create_user(client, headers)

    response = await client.patch(
        f"/users/{created['id']}", headers=headers, json={"status": "active"}
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "active"


async def test_patch_user_invalid_status_transition_returns_409(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    created = await _create_user(client, headers)

    response = await client.patch(
        f"/users/{created['id']}", headers=headers, json={"status": "suspended"}
    )

    assert response.status_code == 409


async def test_delete_user(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    created = await _create_user(client, headers)

    response = await client.delete(f"/users/{created['id']}", headers=headers)
    assert response.status_code == 200

    follow_up = await client.get(f"/users/{created['id']}", headers=headers)
    assert follow_up.status_code == 404
