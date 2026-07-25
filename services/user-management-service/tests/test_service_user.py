"""Tests for :class:`app.services.user.UserService`."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.conflict import ConflictError
from shared_core.notifications.manager import NotificationManager
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserStatus
from app.models.user import User
from app.notifications.user_notifications import UserNotificationService
from app.repositories.activity import UserActivityRepository
from app.repositories.user import UserRepository
from app.services.activity import UserActivityService
from app.services.user import UserService


class _Recorder:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def __call__(self, event: DomainEvent) -> None:
        self.events.append(event)


def _build(db_session: AsyncSession) -> tuple[UserService, _Recorder]:
    recorder = _Recorder()
    activity = UserActivityService(UserActivityRepository(db_session))
    notifications = UserNotificationService(AsyncMock(spec=NotificationManager))
    service = UserService(
        UserRepository(db_session), activity, notifications, publish_event=recorder
    )
    return service, recorder


def _fields() -> dict[str, str]:
    return {
        "username": f"user-{uuid.uuid4().hex[:12]}",
        "email": f"user-{uuid.uuid4().hex}@example.com",
    }


async def test_create_publishes_user_created(db_session: AsyncSession) -> None:
    service, recorder = _build(db_session)
    fields = _fields()

    user = await service.create(
        username=fields["username"],
        email=fields["email"],
        display_name="Test User",
        first_name=None,
        middle_name=None,
        last_name=None,
        phone_number=None,
        timezone="UTC",
        language="en",
        locale="en-US",
    )

    assert user.status == UserStatus.PENDING
    assert any(e.event_name == "UserCreated" for e in recorder.events)


async def test_create_rejects_duplicate_username(db_session: AsyncSession) -> None:
    service, _recorder = _build(db_session)
    fields = _fields()
    await service.create(
        username=fields["username"],
        email=fields["email"],
        display_name=None,
        first_name=None,
        middle_name=None,
        last_name=None,
        phone_number=None,
        timezone="UTC",
        language="en",
        locale="en-US",
    )

    with pytest.raises(ConflictError):
        await service.create(
            username=fields["username"],
            email=f"other-{uuid.uuid4().hex}@example.com",
            display_name=None,
            first_name=None,
            middle_name=None,
            last_name=None,
            phone_number=None,
            timezone="UTC",
            language="en",
            locale="en-US",
        )


async def test_create_rejects_duplicate_email(db_session: AsyncSession) -> None:
    service, _recorder = _build(db_session)
    fields = _fields()
    await service.create(
        username=fields["username"],
        email=fields["email"],
        display_name=None,
        first_name=None,
        middle_name=None,
        last_name=None,
        phone_number=None,
        timezone="UTC",
        language="en",
        locale="en-US",
    )

    with pytest.raises(ConflictError):
        await service.create(
            username=f"other-{uuid.uuid4().hex[:10]}",
            email=fields["email"],
            display_name=None,
            first_name=None,
            middle_name=None,
            last_name=None,
            phone_number=None,
            timezone="UTC",
            language="en",
            locale="en-US",
        )


async def _make_user(service: UserService) -> User:
    fields = _fields()
    return await service.create(
        username=fields["username"],
        email=fields["email"],
        display_name=None,
        first_name=None,
        middle_name=None,
        last_name=None,
        phone_number=None,
        timezone="UTC",
        language="en",
        locale="en-US",
    )


async def test_update_replaces_mutable_fields(db_session: AsyncSession) -> None:
    service, recorder = _build(db_session)
    user = await _make_user(service)

    updated = await service.update(
        user,
        display_name="New Name",
        first_name="First",
        middle_name=None,
        last_name="Last",
        phone_number="+15551234567",
        timezone="America/New_York",
        language="fr",
        locale="fr-FR",
    )

    assert updated.display_name == "New Name"
    assert updated.language == "fr"
    assert any(e.event_name == "UserUpdated" for e in recorder.events)


async def test_patch_applies_only_given_fields(db_session: AsyncSession) -> None:
    service, _recorder = _build(db_session)
    user = await _make_user(service)
    original_email = user.email

    patched = await service.patch(user, display_name="Patched")

    assert patched.display_name == "Patched"
    assert patched.email == original_email


async def test_patch_with_status_transitions(db_session: AsyncSession) -> None:
    service, recorder = _build(db_session)
    user = await _make_user(service)

    patched = await service.patch(user, status=UserStatus.ACTIVE)

    assert patched.status == UserStatus.ACTIVE
    assert any(e.event_name == "UserActivated" for e in recorder.events)


async def test_transition_status_validates(db_session: AsyncSession) -> None:
    service, _recorder = _build(db_session)
    user = await _make_user(service)
    await service.transition_status(user, UserStatus.ACTIVE)

    with pytest.raises(ConflictError):
        await service.transition_status(user, UserStatus.PENDING)


async def test_transition_status_active_to_suspended_publishes_deactivated(
    db_session: AsyncSession,
) -> None:
    service, recorder = _build(db_session)
    user = await _make_user(service)
    await service.transition_status(user, UserStatus.ACTIVE)
    recorder.events.clear()

    await service.transition_status(user, UserStatus.SUSPENDED)

    assert any(e.event_name == "UserDeactivated" for e in recorder.events)


async def test_set_avatar_updates_pointer_and_publishes(db_session: AsyncSession) -> None:
    service, recorder = _build(db_session)
    user = await _make_user(service)

    updated = await service.set_avatar(user, "avatars/key.png")

    assert updated.avatar == "avatars/key.png"
    assert any(e.event_name == "AvatarUpdated" for e in recorder.events)


async def test_delete_soft_deletes_and_publishes(db_session: AsyncSession) -> None:
    service, recorder = _build(db_session)
    user = await _make_user(service)

    await service.delete(user)

    assert await service.get_by_id(user.id) is None
    assert any(e.event_name == "UserDeleted" for e in recorder.events)


async def test_get_by_id_returns_none_for_unknown(db_session: AsyncSession) -> None:
    service, _recorder = _build(db_session)

    assert await service.get_by_id(uuid.uuid4()) is None


async def test_search_returns_matching_user(db_session: AsyncSession) -> None:
    service, _recorder = _build(db_session)
    user = await _make_user(service)

    result = await service.search(
        query=user.username, filters=None, sort_fields=None, page=1, page_size=20
    )

    assert any(u.id == user.id for u in result.items)


async def test_works_with_no_event_bus_configured(db_session: AsyncSession) -> None:
    activity = UserActivityService(UserActivityRepository(db_session))
    notifications = UserNotificationService(AsyncMock(spec=NotificationManager))
    service = UserService(UserRepository(db_session), activity, notifications)
    fields = _fields()

    user = await service.create(
        username=fields["username"],
        email=fields["email"],
        display_name=None,
        first_name=None,
        middle_name=None,
        last_name=None,
        phone_number=None,
        timezone="UTC",
        language="en",
        locale="en-US",
    )

    assert user.id is not None
