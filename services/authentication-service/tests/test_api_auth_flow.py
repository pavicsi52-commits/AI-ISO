"""HTTP-level tests for POST /auth/{register,login,refresh,logout}.

Mirrors the real end-to-end smoke test this service's development was
verified against (register -> login -> refresh -> logout, plus the
MFA challenge round-trip) -- but as an automated, repeatable suite.
"""

from __future__ import annotations

from collections.abc import Callable

from httpx import AsyncClient

from tests.conftest import (
    DEFAULT_TEST_PASSWORD,
    auth_headers,
    login_via_api,
    register_and_login,
    register_via_api,
    unique_email,
)


async def test_register_returns_created_user_summary(client: AsyncClient) -> None:
    email = unique_email()

    response = await client.post(
        "/auth/register",
        json={"email": email, "password": DEFAULT_TEST_PASSWORD, "display_name": "Ada"},
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["email"] == email
    assert data["display_name"] == "Ada"
    assert data["is_email_verified"] is False


async def test_register_rejects_a_weak_password(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register",
        json={"email": unique_email(), "password": "weak", "display_name": None},
    )

    # This service's global exception handlers remap FastAPI's default 422
    # RequestValidationError to 400, matching every other validation failure
    # in this codebase's response shape (see shared_core.exceptions).
    assert response.status_code == 400


async def test_register_rejects_duplicate_email(client: AsyncClient) -> None:
    email = unique_email()
    await register_via_api(client, email=email)

    response = await client.post(
        "/auth/register",
        json={"email": email, "password": DEFAULT_TEST_PASSWORD, "display_name": None},
    )

    assert response.status_code == 409


async def test_login_with_correct_credentials_returns_tokens(client: AsyncClient) -> None:
    _email, tokens = await register_and_login(client)

    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["expires_in"] > 0


async def test_login_with_wrong_password_returns_401(client: AsyncClient) -> None:
    email = unique_email()
    await register_via_api(client, email=email)

    response = await client.post("/auth/login", json={"email": email, "password": "totally-wrong"})

    assert response.status_code == 401


async def test_login_with_unknown_email_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/login", json={"email": unique_email(), "password": DEFAULT_TEST_PASSWORD}
    )

    assert response.status_code == 401


async def test_login_requires_mfa_when_enabled_then_completes(
    client: AsyncClient, totp_code: Callable[[str], str]
) -> None:
    email, tokens = await register_and_login(client)
    enable_response = await client.post(
        "/auth/mfa/enable", headers=auth_headers(tokens["access_token"])
    )
    secret = enable_response.json()["data"]["secret"]
    await client.post(
        "/auth/mfa/verify",
        headers=auth_headers(tokens["access_token"]),
        json={"code": totp_code(secret)},
    )

    challenge = await client.post(
        "/auth/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD}
    )
    assert challenge.status_code == 200
    assert challenge.json()["data"]["mfa_required"] is True

    completed = await login_via_api(client, email=email, mfa_code=totp_code(secret))
    assert completed["access_token"]


async def test_refresh_rotates_tokens(client: AsyncClient) -> None:
    _email, tokens = await register_and_login(client)

    response = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert response.status_code == 200
    new_tokens = response.json()["data"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]


async def test_refresh_with_invalid_token_returns_401(client: AsyncClient) -> None:
    response = await client.post("/auth/refresh", json={"refresh_token": "not-a-real-token"})

    assert response.status_code == 401


async def test_logout_revokes_refresh_token(client: AsyncClient) -> None:
    _email, tokens = await register_and_login(client)

    response = await client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})

    assert response.status_code == 200
    assert response.json()["data"]["success"] is True

    replay = await client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401


async def test_logout_with_no_refresh_token_still_succeeds(client: AsyncClient) -> None:
    response = await client.post("/auth/logout", json={})

    assert response.status_code == 200
    assert response.json()["data"]["success"] is True
