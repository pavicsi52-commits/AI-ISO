"""HTTP-level tests for GET /auth/profile and the sessions/devices/apikeys
CRUD surfaces (GET/DELETE /auth/sessions, /auth/devices, /auth/apikeys).
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user import UserRepository
from tests.conftest import DEFAULT_TEST_PASSWORD, auth_headers, register_and_login


async def test_profile_returns_authenticated_user(client: AsyncClient) -> None:
    email, tokens = await register_and_login(client)

    response = await client.get("/auth/profile", headers=auth_headers(tokens["access_token"]))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["email"] == email
    assert data["mfa_enabled"] is False


async def test_profile_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/auth/profile")

    assert response.status_code == 401


async def test_profile_rejects_a_valid_token_for_a_deleted_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    email, tokens = await register_and_login(client)
    user = await UserRepository(db_session).get_by_email(email)
    assert user is not None
    await UserRepository(db_session).delete(user.id)

    response = await client.get("/auth/profile", headers=auth_headers(tokens["access_token"]))

    assert response.status_code == 401


async def test_profile_rejects_garbage_bearer_token(client: AsyncClient) -> None:
    response = await client.get("/auth/profile", headers=auth_headers("not-a-real-jwt"))

    assert response.status_code == 401


# --- Sessions ---


async def test_list_sessions_includes_the_current_login(client: AsyncClient) -> None:
    _email, tokens = await register_and_login(client)

    response = await client.get("/auth/sessions", headers=auth_headers(tokens["access_token"]))

    assert response.status_code == 200
    assert len(response.json()["data"]) >= 1


async def test_terminate_one_session(client: AsyncClient) -> None:
    _email, tokens = await register_and_login(client)
    headers = auth_headers(tokens["access_token"])
    session_id = (await client.get("/auth/sessions", headers=headers)).json()["data"][0]["id"]

    response = await client.delete(f"/auth/sessions/{session_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["success"] is True


async def test_terminate_session_rejects_someone_elses_session(client: AsyncClient) -> None:
    _email_a, tokens_a = await register_and_login(client)
    _email_b, tokens_b = await register_and_login(client)
    headers_a = auth_headers(tokens_a["access_token"])
    session_id_a = (await client.get("/auth/sessions", headers=headers_a)).json()["data"][0]["id"]

    response = await client.delete(
        f"/auth/sessions/{session_id_a}", headers=auth_headers(tokens_b["access_token"])
    )

    assert response.status_code == 404


async def test_terminate_all_sessions(client: AsyncClient) -> None:
    _email, tokens = await register_and_login(client)
    headers = auth_headers(tokens["access_token"])

    response = await client.delete("/auth/sessions", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["terminated"] >= 1


# --- Devices ---


async def test_list_devices_starts_empty(client: AsyncClient) -> None:
    _email, tokens = await register_and_login(client)

    response = await client.get("/auth/devices", headers=auth_headers(tokens["access_token"]))

    assert response.status_code == 200
    assert response.json()["data"] == []


async def test_revoke_unknown_device_returns_404(client: AsyncClient) -> None:
    _email, tokens = await register_and_login(client)

    response = await client.delete(
        f"/auth/devices/{uuid.uuid4()}", headers=auth_headers(tokens["access_token"])
    )

    assert response.status_code == 404


async def test_revoke_own_device_succeeds(client: AsyncClient) -> None:
    email, _tokens = await register_and_login(client)
    # A device is only recorded when a login presents a fingerprint.
    login_response = await client.post(
        "/auth/login",
        json={
            "email": email,
            "password": DEFAULT_TEST_PASSWORD,
            "device_fingerprint": "fp-http-test",
        },
    )
    assert login_response.status_code == 200
    headers = auth_headers(login_response.json()["data"]["access_token"])
    device_id = (await client.get("/auth/devices", headers=headers)).json()["data"][0]["id"]

    response = await client.delete(f"/auth/devices/{device_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["success"] is True


# --- API keys ---


async def test_create_and_list_api_key(client: AsyncClient) -> None:
    _email, tokens = await register_and_login(client)
    headers = auth_headers(tokens["access_token"])

    created = await client.post(
        "/auth/apikeys",
        headers=headers,
        json={"name": "ci key", "scopes": ["read"], "expires_in_days": None},
    )
    assert created.status_code == 201
    created_data = created.json()["data"]
    assert created_data["raw_key"].startswith("aiios_")

    listed = await client.get("/auth/apikeys", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1
    assert listed.json()["data"][0]["id"] == created_data["id"]


async def test_revoke_api_key(client: AsyncClient) -> None:
    _email, tokens = await register_and_login(client)
    headers = auth_headers(tokens["access_token"])
    created = await client.post(
        "/auth/apikeys",
        headers=headers,
        json={"name": "ci key", "scopes": [], "expires_in_days": None},
    )
    api_key_id = created.json()["data"]["id"]

    response = await client.delete(f"/auth/apikeys/{api_key_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["success"] is True


async def test_revoke_someone_elses_api_key_returns_404(client: AsyncClient) -> None:
    _email_a, tokens_a = await register_and_login(client)
    _email_b, tokens_b = await register_and_login(client)
    created = await client.post(
        "/auth/apikeys",
        headers=auth_headers(tokens_a["access_token"]),
        json={"name": "ci key", "scopes": [], "expires_in_days": None},
    )
    api_key_id = created.json()["data"]["id"]

    response = await client.delete(
        f"/auth/apikeys/{api_key_id}", headers=auth_headers(tokens_b["access_token"])
    )

    assert response.status_code == 404
