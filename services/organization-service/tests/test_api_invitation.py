"""Tests for ``app/api/invitation.py`` (both ``org_router`` and ``router``).

The raw invitation token is never returned over HTTP (only its hash is
persisted) -- by design, the same pattern
``services/user-management-service``'s own invitation flow established.
To exercise the unauthenticated ``accept``/``reject`` endpoints, tests
mint an invitation directly through :class:`InvitationService` against
the test's own SAVEPOINT-scoped ``db_session`` (the same session the
HTTP ``client`` fixture's overridden dependency uses), capturing the
raw token the HTTP layer intentionally never exposes.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import make_org_with_owner

from app.models.enums import MemberRole
from app.models.invitation import OrganizationInvitation
from app.notifications.organization_notifications import OrganizationNotificationService
from app.repositories.activity import OrganizationActivityRepository
from app.repositories.invitation import OrganizationInvitationRepository
from app.repositories.member import OrganizationMemberRepository
from app.repositories.organization_quota import OrganizationQuotaRepository
from app.services.activity import OrganizationActivityService
from app.services.invitation import InvitationService
from app.services.quota import OrganizationQuotaService


async def _direct_invite(
    db_session: AsyncSession,
    app: FastAPI,
    organization_id: uuid.UUID,
    *,
    inviter_id: uuid.UUID,
    email: str = "invitee@example.com",
    role: MemberRole = MemberRole.MEMBER,
) -> tuple[OrganizationInvitation, str]:
    activity = OrganizationActivityService(OrganizationActivityRepository(db_session))
    notifications = OrganizationNotificationService(app.state.notification_manager)
    quotas = OrganizationQuotaService(
        OrganizationQuotaRepository(db_session), OrganizationMemberRepository(db_session), activity
    )
    invitations = InvitationService(
        OrganizationInvitationRepository(db_session),
        OrganizationMemberRepository(db_session),
        activity,
        notifications,
        quotas,
        publish_event=None,
    )
    return await invitations.invite(
        organization_id,
        email=email,
        invited_by=inviter_id,
        role=role,
        department_id=None,
        team_id=None,
        message=None,
        invite_base_url="http://test/organizations/invite/accept",
    )


async def test_invite_member_requires_admin(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)

    forbidden = await client.post(
        f"/organizations/{organization.id}/invite",
        json={"email": "invitee@example.com"},
        headers=auth_headers(outsider),
    )
    assert forbidden.status_code == 403

    allowed = await client.post(
        f"/organizations/{organization.id}/invite",
        json={"email": "invitee@example.com", "role": "admin"},
        headers=auth_headers(owner),
    )
    assert allowed.status_code == 201
    body = allowed.json()["data"]
    assert body["email"] == "invitee@example.com"
    assert body["role"] == "admin"
    assert body["status"] == "pending"


async def test_invite_member_duplicate_pending_conflicts(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)
    payload = {"email": "dup@example.com"}

    first = await client.post(
        f"/organizations/{organization.id}/invite", json=payload, headers=auth_headers(owner)
    )
    assert first.status_code == 201

    second = await client.post(
        f"/organizations/{organization.id}/invite", json=payload, headers=auth_headers(owner)
    )
    assert second.status_code == 409


async def test_accept_invitation_creates_membership(
    db_session: AsyncSession, app: FastAPI, client: AsyncClient
) -> None:
    owner = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)
    _record, raw_token = await _direct_invite(db_session, app, organization.id, inviter_id=owner)

    new_user_id = uuid.uuid4()
    response = await client.post(
        "/organizations/invite/accept", json={"token": raw_token, "user_id": str(new_user_id)}
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["organization_id"] == str(organization.id)


async def test_accept_invitation_invalid_token(client: AsyncClient) -> None:
    response = await client.post(
        "/organizations/invite/accept",
        json={"token": "not-a-real-token", "user_id": str(uuid.uuid4())},
    )
    assert response.status_code == 401


async def test_accept_invitation_over_quota_rejected(
    db_session: AsyncSession,
    app: FastAPI,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)

    quota_response = await client.put(
        f"/organizations/{organization.id}/quotas",
        json={
            "max_users": 1,
            "max_projects": 5,
            "max_assets": 1000,
            "max_storage_gb": 50,
            "max_workflows": 20,
            "max_automation_jobs": 50,
            "max_connectors": 10,
            "max_api_calls_per_day": 10000,
            "max_ai_requests_per_day": 1000,
            "max_plugins": 10,
        },
        headers=auth_headers(owner),
    )
    assert quota_response.status_code == 200

    _record, raw_token = await _direct_invite(db_session, app, organization.id, inviter_id=owner)
    response = await client.post(
        "/organizations/invite/accept",
        json={"token": raw_token, "user_id": str(uuid.uuid4())},
    )
    assert response.status_code == 422


async def test_reject_invitation(
    db_session: AsyncSession, app: FastAPI, client: AsyncClient
) -> None:
    owner = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)
    _record, raw_token = await _direct_invite(db_session, app, organization.id, inviter_id=owner)

    response = await client.post("/organizations/invite/reject", json={"token": raw_token})
    assert response.status_code == 200
    assert response.json()["data"]["success"] is True

    second_accept = await client.post(
        "/organizations/invite/accept", json={"token": raw_token, "user_id": str(uuid.uuid4())}
    )
    assert second_accept.status_code == 401
