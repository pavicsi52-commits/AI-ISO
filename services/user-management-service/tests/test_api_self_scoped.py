"""HTTP-level tests for the caller-self-scoped sub-resources: profile,
preferences, settings, addresses, contacts, metadata, tags, activity.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient


async def _create_caller(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> tuple[uuid.UUID, dict[str, str]]:
    admin_headers = auth_headers(uuid.uuid4())
    response = await client.post(
        "/users",
        headers=admin_headers,
        json={
            "username": f"user-{uuid.uuid4().hex[:12]}",
            "email": f"user-{uuid.uuid4().hex}@example.com",
        },
    )
    assert response.status_code == 201, response.text
    user_id = uuid.UUID(response.json()["data"]["id"])
    return user_id, auth_headers(user_id)


# --- Profile ---


async def test_profile_get_and_update(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    _user_id, headers = await _create_caller(client, auth_headers)

    initial = await client.get("/users/profile", headers=headers)
    assert initial.status_code == 200

    updated = await client.put(
        "/users/profile", headers=headers, json={"biography": "Hello", "job_title": "Engineer"}
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["biography"] == "Hello"


# --- Preferences ---


async def test_preferences_get_and_update(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    _user_id, headers = await _create_caller(client, auth_headers)

    await client.get("/users/preferences", headers=headers)
    updated = await client.put("/users/preferences", headers=headers, json={"theme": "dark"})

    assert updated.status_code == 200
    assert updated.json()["data"]["theme"] == "dark"


# --- Settings ---


async def test_settings_get_and_update(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    _user_id, headers = await _create_caller(client, auth_headers)

    await client.get("/users/settings", headers=headers)
    updated = await client.put(
        "/users/settings", headers=headers, json={"favorites": ["dashboard"]}
    )

    assert updated.status_code == 200
    assert updated.json()["data"]["favorites"] == ["dashboard"]


# --- Addresses ---


async def test_address_add_list_remove(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    _user_id, headers = await _create_caller(client, auth_headers)

    created = await client.post(
        "/users/addresses", headers=headers, json={"line1": "1 Main St", "country": "US"}
    )
    assert created.status_code == 201
    address_id = created.json()["data"]["id"]

    listed = await client.get("/users/addresses", headers=headers)
    assert len(listed.json()["data"]) == 1

    removed = await client.delete(f"/users/addresses/{address_id}", headers=headers)
    assert removed.status_code == 200


# --- Contacts ---


async def test_contact_add_list_remove(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    _user_id, headers = await _create_caller(client, auth_headers)

    created = await client.post(
        "/users/contacts",
        headers=headers,
        json={"contact_type": "phone", "value": "+15551234567"},
    )
    assert created.status_code == 201
    contact_id = created.json()["data"]["id"]

    listed = await client.get("/users/contacts", headers=headers)
    assert len(listed.json()["data"]) == 1

    removed = await client.delete(f"/users/contacts/{contact_id}", headers=headers)
    assert removed.status_code == 200


async def test_contact_add_rejects_malformed_phone(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    _user_id, headers = await _create_caller(client, auth_headers)

    response = await client.post(
        "/users/contacts", headers=headers, json={"contact_type": "phone", "value": "not-a-phone"}
    )

    assert response.status_code == 400


# --- Metadata ---


async def test_metadata_set_list_delete(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    _user_id, headers = await _create_caller(client, auth_headers)

    set_response = await client.put(
        "/users/metadata/onboarded", headers=headers, json={"value": "true"}
    )
    assert set_response.status_code == 200

    listed = await client.get("/users/metadata", headers=headers)
    assert len(listed.json()["data"]) == 1

    deleted = await client.delete("/users/metadata/onboarded", headers=headers)
    assert deleted.status_code == 200


# --- Tags ---


async def test_tag_assign_list_remove(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    _user_id, headers = await _create_caller(client, auth_headers)

    created = await client.post("/users/tags", headers=headers, json={"label": "vip"})
    assert created.status_code == 201
    tag_id = created.json()["data"]["id"]

    listed = await client.get("/users/tags", headers=headers)
    assert len(listed.json()["data"]) == 1

    removed = await client.delete(f"/users/tags/{tag_id}", headers=headers)
    assert removed.status_code == 200


async def test_tag_assign_duplicate_returns_409(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    _user_id, headers = await _create_caller(client, auth_headers)
    await client.post("/users/tags", headers=headers, json={"label": "vip"})

    response = await client.post("/users/tags", headers=headers, json={"label": "vip"})

    assert response.status_code == 409


# --- Activity ---


async def test_activity_list_reflects_prior_operations(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    _user_id, headers = await _create_caller(client, auth_headers)
    await client.put("/users/profile", headers=headers, json={"biography": "Hi"})

    response = await client.get("/users/activity", headers=headers)

    assert response.status_code == 200
    assert len(response.json()["data"]) >= 1
