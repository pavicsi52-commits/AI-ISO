"""HTTP-level tests for POST /users/invite, /resend, /accept, /reject."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from unittest.mock import AsyncMock

from httpx import AsyncClient
from shared_core.notifications.manager import NotificationManager
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.user_notifications import UserNotificationService
from app.repositories.activity import UserActivityRepository
from app.repositories.invitation import UserInvitationRepository
from app.repositories.user import UserRepository
from app.services.activity import UserActivityService
from app.services.invitation import InvitationService
from app.services.user import UserService


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


def _invitation_service(db_session: AsyncSession) -> InvitationService:
    """Build an :class:`InvitationService` on the same session ``client``'s
    requests share (the ``app`` fixture overrides ``get_db_session`` to
    yield this exact session) -- so a raw token minted here is visible to
    the HTTP layer too, exactly like the emailed link's token would be.
    """
    activity = UserActivityService(UserActivityRepository(db_session))
    notifications = UserNotificationService(AsyncMock(spec=NotificationManager))
    users = UserService(UserRepository(db_session), activity, notifications)
    return InvitationService(UserInvitationRepository(db_session), users, activity, notifications)


async def test_invite_user(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    _user_id, headers = await _create_caller(client, auth_headers)
    email = f"invitee-{uuid.uuid4().hex}@example.com"

    response = await client.post("/users/invite", headers=headers, json={"email": email})

    assert response.status_code == 201
    assert response.json()["data"]["status"] == "pending"


async def test_invite_requires_authentication(client: AsyncClient) -> None:
    response = await client.post("/users/invite", json={"email": "x@example.com"})

    assert response.status_code == 401


async def test_resend_invitation(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    _user_id, headers = await _create_caller(client, auth_headers)
    email = f"invitee-{uuid.uuid4().hex}@example.com"
    await client.post("/users/invite", headers=headers, json={"email": email})

    response = await client.post("/users/invite/resend", headers=headers, json={"email": email})

    assert response.status_code == 200


async def test_accept_invitation_creates_user(
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
    db_session: AsyncSession,
) -> None:
    inviter_id, _headers = await _create_caller(client, auth_headers)
    email = f"invitee-{uuid.uuid4().hex}@example.com"
    service = _invitation_service(db_session)
    _record, raw_token = await service.invite(
        email, invited_by=inviter_id, message=None, invite_base_url="https://example.com/accept"
    )

    # accept is unauthenticated by design -- the token itself is the credential.
    response = await client.post(
        "/users/invite/accept",
        json={
            "token": raw_token,
            "username": f"newuser-{uuid.uuid4().hex[:8]}",
            "display_name": "New User",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["email"] == email


async def test_accept_invitation_rejects_invalid_token(client: AsyncClient) -> None:
    response = await client.post(
        "/users/invite/accept",
        json={"token": "not-a-real-token", "username": "someone", "display_name": None},
    )

    assert response.status_code == 401


async def test_reject_invitation(
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
    db_session: AsyncSession,
) -> None:
    inviter_id, _headers = await _create_caller(client, auth_headers)
    email = f"invitee-{uuid.uuid4().hex}@example.com"
    service = _invitation_service(db_session)
    _record, raw_token = await service.invite(
        email, invited_by=inviter_id, message=None, invite_base_url="https://example.com/accept"
    )

    response = await client.post("/users/invite/reject", json={"token": raw_token})

    assert response.status_code == 200
    assert response.json()["data"]["success"] is True
