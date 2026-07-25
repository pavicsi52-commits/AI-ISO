"""Direct service-layer tests for ``app/services/invitation.py`` branches
the API-layer tests (``tests/test_api_invitation.py``) don't reach:
resend, expiry, and double-resolution.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.exceptions.authentication import AuthenticationError
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import make_org

from app.notifications.organization_notifications import OrganizationNotificationService
from app.repositories.activity import OrganizationActivityRepository
from app.repositories.invitation import OrganizationInvitationRepository
from app.repositories.member import OrganizationMemberRepository
from app.repositories.organization_quota import OrganizationQuotaRepository
from app.services.activity import OrganizationActivityService
from app.services.invitation import InvitationService
from app.services.quota import OrganizationQuotaService


class _NullNotificationManager:
    async def send(self, *args: object, **kwargs: object) -> None:
        return None


def _make_service(db_session: AsyncSession) -> InvitationService:
    activity = OrganizationActivityService(OrganizationActivityRepository(db_session))
    notifications = OrganizationNotificationService(_NullNotificationManager())  # type: ignore[arg-type]
    quotas = OrganizationQuotaService(
        OrganizationQuotaRepository(db_session), OrganizationMemberRepository(db_session), activity
    )
    return InvitationService(
        OrganizationInvitationRepository(db_session),
        OrganizationMemberRepository(db_session),
        activity,
        notifications,
        quotas,
        publish_event=None,
    )


async def test_resend_issues_a_fresh_token(db_session: AsyncSession) -> None:
    organization = await make_org(db_session)
    inviter = uuid.uuid4()
    service = _make_service(db_session)
    record, original_token = await service.invite(
        organization.id,
        email="resend@example.com",
        invited_by=inviter,
        role=__import__("app.models.enums", fromlist=["MemberRole"]).MemberRole.MEMBER,
        department_id=None,
        team_id=None,
        message=None,
        invite_base_url="http://test/accept",
    )
    assert record.resend_count == 0

    new_token = await service.resend(
        organization.id, "resend@example.com", invite_base_url="http://test/accept"
    )
    assert new_token != original_token
    assert record.resend_count == 1

    # The old token no longer resolves; the new one does.
    with pytest.raises(AuthenticationError):
        await service.accept(token=original_token, user_id=uuid.uuid4())
    member = await service.accept(token=new_token, user_id=uuid.uuid4())
    assert member.organization_id == organization.id


async def test_resend_unknown_email_raises(db_session: AsyncSession) -> None:
    organization = await make_org(db_session)
    service = _make_service(db_session)
    with pytest.raises(AuthenticationError):
        await service.resend(
            organization.id, "nobody@example.com", invite_base_url="http://test/accept"
        )


async def test_accept_expired_invitation_raises_and_marks_expired(
    db_session: AsyncSession,
) -> None:
    organization = await make_org(db_session)
    inviter = uuid.uuid4()
    service = _make_service(db_session)
    record, raw_token = await service.invite(
        organization.id,
        email="expired@example.com",
        invited_by=inviter,
        role=__import__("app.models.enums", fromlist=["MemberRole"]).MemberRole.MEMBER,
        department_id=None,
        team_id=None,
        message=None,
        invite_base_url="http://test/accept",
    )
    record.expires_at = datetime.now(UTC) - timedelta(days=1)

    with pytest.raises(AuthenticationError):
        await service.accept(token=raw_token, user_id=uuid.uuid4())
    assert record.status.value == "expired"


async def test_reject_unknown_token_raises(db_session: AsyncSession) -> None:
    service = _make_service(db_session)
    with pytest.raises(AuthenticationError):
        await service.reject("not-a-real-token")
