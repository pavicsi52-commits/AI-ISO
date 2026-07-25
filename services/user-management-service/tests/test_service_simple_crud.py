"""Tests for the smaller per-entity CRUD services: profile, preferences,
settings, address, contact, metadata, tag, note, activity.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.enums import ActivityType, AddressType, ContactType
from app.models.user import User
from app.repositories.activity import UserActivityRepository
from app.repositories.address import UserAddressRepository
from app.repositories.contact import UserContactRepository
from app.repositories.metadata import UserMetadataRepository
from app.repositories.note import UserNoteRepository
from app.repositories.preferences import UserPreferencesRepository
from app.repositories.profile import UserProfileRepository
from app.repositories.settings import UserSettingsRepository
from app.repositories.tag import UserTagRepository
from app.repositories.user import UserRepository
from app.services.activity import UserActivityService
from app.services.address import UserAddressService
from app.services.contact import UserContactService
from app.services.metadata import UserMetadataService
from app.services.note import UserNoteService
from app.services.preferences import UserPreferencesService
from app.services.profile import UserProfileService
from app.services.settings import UserSettingsService
from app.services.tag import UserTagService


async def _make_user(session: AsyncSession) -> User:
    return await UserRepository(session).create(
        User(
            username=f"user-{uuid.uuid4().hex[:12]}",
            email=f"user-{uuid.uuid4().hex}@example.com",
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )


# --- Profile ---


async def test_profile_get_or_create_then_update(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    activity = UserActivityService(UserActivityRepository(db_session))
    service = UserProfileService(UserProfileRepository(db_session), activity)

    created = await service.get_or_create(user.id)
    assert created.user_id == user.id

    updated = await service.update(
        user.id,
        biography="Bio",
        job_title="Engineer",
        department="R&D",
        employee_id="E1",
        manager_id=None,
        custom_fields={"k": "v"},
    )
    assert updated.biography == "Bio"
    assert updated.id == created.id

    entries = await activity.list_recent(user.id)
    assert any(e.activity_type == ActivityType.PROFILE_UPDATED for e in entries)


# --- Preferences ---


async def test_preferences_get_or_create_then_update(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    activity = UserActivityService(UserActivityRepository(db_session))
    service = UserPreferencesService(UserPreferencesRepository(db_session), activity)

    await service.get_or_create(user.id)
    updated = await service.update(
        user.id,
        language="fr",
        theme="dark",
        timezone="UTC",
        date_format="DD/MM/YYYY",
        time_format="12h",
        dashboard_preferences={},
        notification_preferences={},
        accessibility={},
        default_organization_id=None,
        default_project_id=None,
    )

    assert updated.language == "fr"
    assert updated.theme == "dark"

    entries = await activity.list_recent(user.id)
    assert any(e.activity_type == ActivityType.PREFERENCES_UPDATED for e in entries)


# --- Settings ---


async def test_settings_get_or_create_then_update(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    service = UserSettingsService(UserSettingsRepository(db_session))

    await service.get_or_create(user.id)
    updated = await service.update(
        user.id,
        display_settings={},
        privacy={},
        security_preferences={},
        default_views={},
        shortcuts={},
        favorites=["fav1"],
        feature_flags={"beta": True},
    )

    assert updated.favorites == ["fav1"]
    assert updated.feature_flags == {"beta": True}


# --- Address ---


async def test_address_add_list_remove(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    service = UserAddressService(UserAddressRepository(db_session))

    address = await service.add(
        user.id,
        address_type=AddressType.HOME,
        line1="1 Main St",
        line2=None,
        city="Anytown",
        state_province=None,
        postal_code=None,
        country="US",
        is_primary=True,
    )
    assert len(await service.list_for_user(user.id)) == 1

    await service.remove(user.id, address.id)
    assert await service.list_for_user(user.id) == []


async def test_address_remove_rejects_wrong_owner(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session)
    other = await _make_user(db_session)
    service = UserAddressService(UserAddressRepository(db_session))
    address = await service.add(
        owner.id,
        address_type=AddressType.HOME,
        line1="1 Main St",
        line2=None,
        city=None,
        state_province=None,
        postal_code=None,
        country=None,
        is_primary=False,
    )

    with pytest.raises(NotFoundError):
        await service.remove(other.id, address.id)


# --- Contact ---


async def test_contact_add_list_remove(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    service = UserContactService(UserContactRepository(db_session))

    contact = await service.add(
        user.id, contact_type=ContactType.PHONE, value="+15551234567", label="work", is_primary=True
    )
    assert len(await service.list_for_user(user.id)) == 1

    await service.remove(user.id, contact.id)
    assert await service.list_for_user(user.id) == []


async def test_contact_remove_rejects_wrong_owner(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session)
    other = await _make_user(db_session)
    service = UserContactService(UserContactRepository(db_session))
    contact = await service.add(
        owner.id,
        contact_type=ContactType.EMAIL,
        value="a@example.com",
        label=None,
        is_primary=False,
    )

    with pytest.raises(NotFoundError):
        await service.remove(other.id, contact.id)


# --- Metadata ---


async def test_metadata_set_list_remove(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    service = UserMetadataService(UserMetadataRepository(db_session))

    await service.set(user.id, "onboarded", "true")
    assert len(await service.list_for_user(user.id)) == 1

    await service.set(user.id, "onboarded", "false")
    entries = await service.list_for_user(user.id)
    assert len(entries) == 1
    assert entries[0].value == "false"

    await service.remove(user.id, "onboarded")
    assert await service.list_for_user(user.id) == []


async def test_metadata_remove_missing_key_is_a_no_op(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    service = UserMetadataService(UserMetadataRepository(db_session))

    await service.remove(user.id, "does-not-exist")


# --- Tag ---


async def test_tag_assign_list_remove(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    service = UserTagService(UserTagRepository(db_session))

    tag = await service.assign(user.id, label="vip", category="tier")
    assert len(await service.list_for_user(user.id)) == 1

    await service.remove(user.id, tag.id)
    assert await service.list_for_user(user.id) == []


async def test_tag_assign_rejects_duplicate_label(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    service = UserTagService(UserTagRepository(db_session))
    await service.assign(user.id, label="vip", category=None)

    with pytest.raises(ConflictError):
        await service.assign(user.id, label="vip", category=None)


async def test_tag_remove_rejects_wrong_owner(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session)
    other = await _make_user(db_session)
    service = UserTagService(UserTagRepository(db_session))
    tag = await service.assign(owner.id, label="vip", category=None)

    with pytest.raises(NotFoundError):
        await service.remove(other.id, tag.id)


# --- Note ---


async def test_note_add_list_remove(db_session: AsyncSession) -> None:
    subject = await _make_user(db_session)
    author = await _make_user(db_session)
    service = UserNoteService(UserNoteRepository(db_session))

    note = await service.add(subject.id, author_id=author.id, body="Note body")
    assert len(await service.list_for_user(subject.id)) == 1

    await service.remove(subject.id, note.id)
    assert await service.list_for_user(subject.id) == []


async def test_note_remove_rejects_wrong_subject(db_session: AsyncSession) -> None:
    subject = await _make_user(db_session)
    other_subject = await _make_user(db_session)
    author = await _make_user(db_session)
    service = UserNoteService(UserNoteRepository(db_session))
    note = await service.add(subject.id, author_id=author.id, body="Note body")

    with pytest.raises(NotFoundError):
        await service.remove(other_subject.id, note.id)


# --- Activity ---


async def test_activity_record_and_list_recent(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    service = UserActivityService(UserActivityRepository(db_session))

    await service.record(user.id, activity_type=ActivityType.PROFILE_UPDATED)
    await service.record(user.id, activity_type=ActivityType.STATUS_CHANGED, detail={"a": 1})

    entries = await service.list_recent(user.id, limit=1)
    assert len(entries) == 1
