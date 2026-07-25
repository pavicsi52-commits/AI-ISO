"""HTTP-level tests for POST /auth/{forgot-password,reset-password,verify-email,
resend-verification}.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.password import PasswordHistoryRepository, PasswordResetTokenRepository
from app.repositories.user import UserRepository
from app.repositories.verification import EmailVerificationTokenRepository
from app.services.passwords import PasswordService
from app.services.verification import VerificationService
from tests.conftest import DEFAULT_TEST_PASSWORD, login_via_api, register_via_api, unique_email


async def test_forgot_password_always_returns_success(client: AsyncClient) -> None:
    email = unique_email()
    await register_via_api(client, email=email)

    response = await client.post("/auth/forgot-password", json={"email": email})

    assert response.status_code == 200
    assert response.json()["data"]["success"] is True


async def test_forgot_password_does_not_reveal_unknown_email(client: AsyncClient) -> None:
    response = await client.post("/auth/forgot-password", json={"email": unique_email()})

    assert response.status_code == 200
    assert response.json()["data"]["success"] is True


async def test_reset_password_round_trip(client: AsyncClient, db_session: AsyncSession) -> None:
    email = unique_email()
    await register_via_api(client, email=email)
    await client.post("/auth/forgot-password", json={"email": email})

    # The raw reset token is only ever emailed, never returned by the API;
    # this test's own DB session sees the just-registered user (the same
    # transaction the app's overridden dependency shares), so it mints a
    # fresh raw token through the real service layer to consume, exactly
    # as the emailed link's token would have been produced.
    user = await UserRepository(db_session).get_by_email(email)
    assert user is not None
    service = PasswordService(
        PasswordHistoryRepository(db_session), PasswordResetTokenRepository(db_session)
    )
    raw_token = await service.create_reset_token(user)

    response = await client.post(
        "/auth/reset-password", json={"token": raw_token, "new_password": "BrandNewSecret!45"}
    )

    assert response.status_code == 200
    relogin = await login_via_api(client, email=email, password="BrandNewSecret!45")
    assert relogin["access_token"]


async def test_reset_password_with_invalid_token_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/reset-password",
        json={"token": "not-a-real-token", "new_password": "BrandNewSecret!45"},
    )

    assert response.status_code == 401


async def test_resend_verification_always_returns_success(client: AsyncClient) -> None:
    email = unique_email()
    await register_via_api(client, email=email)

    response = await client.post("/auth/resend-verification", json={"email": email})

    assert response.status_code == 200
    assert response.json()["data"]["success"] is True


async def test_verify_email_round_trip(client: AsyncClient, db_session: AsyncSession) -> None:
    email = unique_email()
    await register_via_api(client, email=email)

    user = await UserRepository(db_session).get_by_email(email)
    assert user is not None
    service = VerificationService(EmailVerificationTokenRepository(db_session))
    raw_token = await service.create_token(user)

    response = await client.post("/auth/verify-email", json={"token": raw_token})

    assert response.status_code == 200
    assert response.json()["data"]["success"] is True


async def test_verify_email_with_invalid_token_returns_401(client: AsyncClient) -> None:
    response = await client.post("/auth/verify-email", json={"token": "not-a-real-token"})

    assert response.status_code == 401


async def test_reset_password_rejects_reused_password(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    email = unique_email()
    await register_via_api(client, email=email)

    user = await UserRepository(db_session).get_by_email(email)
    assert user is not None
    service = PasswordService(
        PasswordHistoryRepository(db_session), PasswordResetTokenRepository(db_session)
    )
    raw_token = await service.create_reset_token(user)

    response = await client.post(
        "/auth/reset-password", json={"token": raw_token, "new_password": DEFAULT_TEST_PASSWORD}
    )

    assert response.status_code == 400
