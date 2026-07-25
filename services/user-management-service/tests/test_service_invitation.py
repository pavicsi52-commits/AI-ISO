"""Tests for :class:`app.services.invitation.InvitationService`."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.exceptions.conflict import ConflictError
from shared_core.notifications.manager import NotificationManager
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.enums import InvitationStatus
from app.models.user import User
from app.notifications.user_notifications import UserNotificationService
from app.repositories.activity import UserActivityRepository
from app.repositories.invitation import UserInvitationRepository
from app.repositories.user import UserRepository
from app.services.activity import UserActivityService
from app.services.invitation import InvitationService
from app.services.user import UserService


class _Recorder:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def __call__(self, event: DomainEvent) -> None:
        self.events.append(event)


async def _make_user(session: AsyncSession) -> User:
    return await UserRepository(session).create(
        User(
            username=f"user-{uuid.uuid4().hex[:12]}",
            email=f"user-{uuid.uuid4().hex}@example.com",
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )


def _build(db_session: AsyncSession) -> tuple[InvitationService, _Recorder]:
    recorder = _Recorder()
    activity = UserActivityService(UserActivityRepository(db_session))
    notifications = UserNotificationService(AsyncMock(spec=NotificationManager))
    users = UserService(UserRepository(db_session), activity, notifications)
    service = InvitationService(
        UserInvitationRepository(db_session),
        users,
        activity,
        notifications,
        publish_event=recorder,
    )
    return service, recorder


async def test_invite_creates_pending_invitation_and_publishes(db_session: AsyncSession) -> None:
    service, recorder = _build(db_session)
    inviter = await _make_user(db_session)
    email = f"invitee-{uuid.uuid4().hex}@example.com"

    record, raw_token = await service.invite(
        email,
        invited_by=inviter.id,
        message="Welcome",
        invite_base_url="https://example.com/accept",
    )

    assert record.status == InvitationStatus.PENDING
    assert len(raw_token) > 0
    assert any(e.event_name == "UserInvited" for e in recorder.events)


async def test_invite_rejects_duplicate_pending(db_session: AsyncSession) -> None:
    service, _recorder = _build(db_session)
    inviter = await _make_user(db_session)
    email = f"invitee-{uuid.uuid4().hex}@example.com"
    await service.invite(
        email, invited_by=inviter.id, message=None, invite_base_url="https://example.com/accept"
    )

    with pytest.raises(ConflictError):
        await service.invite(
            email, invited_by=inviter.id, message=None, invite_base_url="https://example.com/accept"
        )


async def test_resend_issues_a_fresh_token(db_session: AsyncSession) -> None:
    service, _recorder = _build(db_session)
    inviter = await _make_user(db_session)
    email = f"invitee-{uuid.uuid4().hex}@example.com"
    _record, first_token = await service.invite(
        email, invited_by=inviter.id, message=None, invite_base_url="https://example.com/accept"
    )

    second_token = await service.resend(email, invite_base_url="https://example.com/accept")

    assert second_token != first_token


async def test_resend_rejects_unknown_email(db_session: AsyncSession) -> None:
    service, _recorder = _build(db_session)

    with pytest.raises(AuthenticationError):
        await service.resend("nobody@example.com", invite_base_url="https://example.com/accept")


async def test_accept_creates_user_and_publishes(db_session: AsyncSession) -> None:
    service, recorder = _build(db_session)
    inviter = await _make_user(db_session)
    email = f"invitee-{uuid.uuid4().hex}@example.com"
    _record, raw_token = await service.invite(
        email, invited_by=inviter.id, message=None, invite_base_url="https://example.com/accept"
    )

    user = await service.accept(
        token=raw_token, username=f"newuser-{uuid.uuid4().hex[:8]}", display_name="New User"
    )

    assert user.email == email
    assert any(e.event_name == "InvitationAccepted" for e in recorder.events)


async def test_accept_rejects_invalid_token(db_session: AsyncSession) -> None:
    service, _recorder = _build(db_session)

    with pytest.raises(AuthenticationError):
        await service.accept(token="not-a-real-token", username="someone", display_name=None)


async def test_accept_rejects_already_accepted_token(db_session: AsyncSession) -> None:
    service, _recorder = _build(db_session)
    inviter = await _make_user(db_session)
    email = f"invitee-{uuid.uuid4().hex}@example.com"
    _record, raw_token = await service.invite(
        email, invited_by=inviter.id, message=None, invite_base_url="https://example.com/accept"
    )
    await service.accept(
        token=raw_token, username=f"newuser-{uuid.uuid4().hex[:8]}", display_name=None
    )

    with pytest.raises(AuthenticationError):
        await service.accept(
            token=raw_token, username=f"another-{uuid.uuid4().hex[:8]}", display_name=None
        )


async def test_reject_marks_invitation_rejected(db_session: AsyncSession) -> None:
    service, _recorder = _build(db_session)
    inviter = await _make_user(db_session)
    email = f"invitee-{uuid.uuid4().hex}@example.com"
    _record, raw_token = await service.invite(
        email, invited_by=inviter.id, message=None, invite_base_url="https://example.com/accept"
    )

    rejected = await service.reject(raw_token)

    assert rejected.status == InvitationStatus.REJECTED


async def test_reject_rejects_invalid_token(db_session: AsyncSession) -> None:
    service, _recorder = _build(db_session)

    with pytest.raises(AuthenticationError):
        await service.reject("not-a-real-token")
