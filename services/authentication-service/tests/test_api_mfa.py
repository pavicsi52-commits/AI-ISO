"""HTTP-level tests for POST /auth/mfa/{enable,verify,disable}."""

from __future__ import annotations

from collections.abc import Callable

from httpx import AsyncClient

from tests.conftest import auth_headers, register_and_login


async def test_enable_returns_secret_and_recovery_codes(client: AsyncClient) -> None:
    _email, tokens = await register_and_login(client)

    response = await client.post("/auth/mfa/enable", headers=auth_headers(tokens["access_token"]))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["secret"]
    assert data["otpauth_uri"].startswith("otpauth://totp/")
    assert len(data["recovery_codes"]) > 0


async def test_verify_with_correct_code_enables_mfa(
    client: AsyncClient, totp_code: Callable[[str], str]
) -> None:
    _email, tokens = await register_and_login(client)
    enable_response = await client.post(
        "/auth/mfa/enable", headers=auth_headers(tokens["access_token"])
    )
    secret = enable_response.json()["data"]["secret"]

    response = await client.post(
        "/auth/mfa/verify",
        headers=auth_headers(tokens["access_token"]),
        json={"code": totp_code(secret)},
    )

    assert response.status_code == 200
    assert response.json()["data"]["success"] is True


async def test_verify_with_wrong_code_returns_401(client: AsyncClient) -> None:
    _email, tokens = await register_and_login(client)
    await client.post("/auth/mfa/enable", headers=auth_headers(tokens["access_token"]))

    response = await client.post(
        "/auth/mfa/verify", headers=auth_headers(tokens["access_token"]), json={"code": "000000"}
    )

    assert response.status_code == 401


async def test_disable_requires_valid_code(
    client: AsyncClient, totp_code: Callable[[str], str]
) -> None:
    _email, tokens = await register_and_login(client)
    enable_response = await client.post(
        "/auth/mfa/enable", headers=auth_headers(tokens["access_token"])
    )
    secret = enable_response.json()["data"]["secret"]
    await client.post(
        "/auth/mfa/verify",
        headers=auth_headers(tokens["access_token"]),
        json={"code": totp_code(secret)},
    )

    rejected = await client.post(
        "/auth/mfa/disable", headers=auth_headers(tokens["access_token"]), json={"code": "000000"}
    )
    assert rejected.status_code == 401

    accepted = await client.post(
        "/auth/mfa/disable",
        headers=auth_headers(tokens["access_token"]),
        json={"code": totp_code(secret)},
    )
    assert accepted.status_code == 200
    assert accepted.json()["data"]["success"] is True


async def test_mfa_endpoints_require_authentication(client: AsyncClient) -> None:
    response = await client.post("/auth/mfa/enable")

    assert response.status_code == 401
