"""Repository-layer tests: the custom finder/listing methods each repository
adds on top of ``shared_core.database.repository.BaseRepository``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from shared_core.enums.job_status import JobStatus
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.activity import UserActivityEntry
from app.models.address import UserAddress
from app.models.avatar import UserAvatar
from app.models.contact import UserContact
from app.models.enums import (
    ActivityType,
    AddressType,
    ContactType,
    ExportFormat,
    ImportFormat,
    InvitationStatus,
)
from app.models.export_job import UserExportJob
from app.models.import_job import UserImportJob
from app.models.invitation import UserInvitation
from app.models.metadata import UserMetadataEntry
from app.models.note import UserNote
from app.models.preferences import UserPreferences
from app.models.profile import UserProfile
from app.models.settings import UserSettings
from app.models.tag import UserTag
from app.models.user import User
from app.repositories.activity import UserActivityRepository
from app.repositories.address import UserAddressRepository
from app.repositories.avatar import UserAvatarRepository
from app.repositories.contact import UserContactRepository
from app.repositories.export_job import UserExportJobRepository
from app.repositories.import_job import UserImportJobRepository
from app.repositories.invitation import UserInvitationRepository
from app.repositories.metadata import UserMetadataRepository
from app.repositories.note import UserNoteRepository
from app.repositories.preferences import UserPreferencesRepository
from app.repositories.profile import UserProfileRepository
from app.repositories.settings import UserSettingsRepository
from app.repositories.tag import UserTagRepository
from app.repositories.user import UserRepository


async def _make_user(session: AsyncSession, **overrides: object) -> User:
    values: dict[str, object] = {
        "username": f"user-{uuid.uuid4().hex[:12]}",
        "email": f"user-{uuid.uuid4().hex}@example.com",
        "organization_id": DEFAULT_ORGANIZATION_ID,
    }
    values.update(overrides)
    return await UserRepository(session).create(User(**values))


async def test_user_repository_lookups(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = UserRepository(db_session)

    by_username = await repo.get_by_username(user.username)
    by_email = await repo.get_by_email(user.email)
    assert by_username is not None
    assert by_email is not None
    assert by_username.id == user.id
    assert by_email.id == user.id
    assert await repo.get_by_username("nobody") is None
    assert await repo.get_by_email("nobody@example.com") is None


async def test_profile_repository_get_for_user(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = UserProfileRepository(db_session)
    await repo.create(UserProfile(user_id=user.id, organization_id=DEFAULT_ORGANIZATION_ID))

    found = await repo.get_for_user(user.id)

    assert found is not None
    assert found.user_id == user.id
    assert await repo.get_for_user(uuid.uuid4()) is None


async def test_preferences_repository_get_for_user(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = UserPreferencesRepository(db_session)
    await repo.create(UserPreferences(user_id=user.id, organization_id=DEFAULT_ORGANIZATION_ID))

    found = await repo.get_for_user(user.id)

    assert found is not None


async def test_settings_repository_get_for_user(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = UserSettingsRepository(db_session)
    await repo.create(UserSettings(user_id=user.id, organization_id=DEFAULT_ORGANIZATION_ID))

    found = await repo.get_for_user(user.id)

    assert found is not None


async def test_address_repository_list_for_user(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = UserAddressRepository(db_session)
    await repo.create(
        UserAddress(
            user_id=user.id,
            address_type=AddressType.HOME,
            line1="1 Main St",
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )

    listed = await repo.list_for_user(user.id)

    assert len(listed) == 1


async def test_contact_repository_list_for_user(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = UserContactRepository(db_session)
    await repo.create(
        UserContact(
            user_id=user.id,
            contact_type=ContactType.PHONE,
            value="+15551234567",
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )

    listed = await repo.list_for_user(user.id)

    assert len(listed) == 1


async def test_metadata_repository_lookups(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = UserMetadataRepository(db_session)
    await repo.create(
        UserMetadataEntry(
            user_id=user.id, key="k1", value="v1", organization_id=DEFAULT_ORGANIZATION_ID
        )
    )

    assert (await repo.get_by_key(user.id, "k1")) is not None
    assert (await repo.get_by_key(user.id, "missing")) is None
    assert len(await repo.list_for_user(user.id)) == 1


async def test_avatar_repository_current_and_history(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = UserAvatarRepository(db_session)
    old = await repo.create(
        UserAvatar(
            user_id=user.id,
            storage_key="old.png",
            content_type="image/png",
            size_bytes=10,
            is_current=False,
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )
    current = await repo.create(
        UserAvatar(
            user_id=user.id,
            storage_key="new.png",
            content_type="image/png",
            size_bytes=10,
            is_current=True,
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )

    found_current = await repo.get_current_for_user(user.id)
    history = await repo.list_history_for_user(user.id)

    assert found_current is not None
    assert found_current.id == current.id
    assert {a.id for a in history} == {old.id, current.id}


async def test_invitation_repository_lookups(db_session: AsyncSession) -> None:
    inviter = await _make_user(db_session)
    repo = UserInvitationRepository(db_session)
    invitation = await repo.create(
        UserInvitation(
            email="invitee@example.com",
            invited_by=inviter.id,
            token_hash="hash1",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )

    by_token = await repo.get_by_token_hash("hash1")
    by_email = await repo.get_pending_for_email("invitee@example.com")
    assert by_token is not None
    assert by_email is not None
    assert by_token.id == invitation.id
    assert by_email.id == invitation.id
    assert invitation in await repo.list_pending()


async def test_import_job_repository_list_for_requester(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = UserImportJobRepository(db_session)
    await repo.create(
        UserImportJob(
            requested_by=user.id,
            source_format=ImportFormat.CSV,
            source_storage_key="k",
            status=JobStatus.QUEUED,
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )

    listed = await repo.list_for_requester(user.id)

    assert len(listed) == 1


async def test_export_job_repository_list_for_requester(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = UserExportJobRepository(db_session)
    await repo.create(
        UserExportJob(
            requested_by=user.id,
            target_format=ExportFormat.CSV,
            status=JobStatus.QUEUED,
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )

    listed = await repo.list_for_requester(user.id)

    assert len(listed) == 1


async def test_activity_repository_list_recent_for_user(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = UserActivityRepository(db_session)
    for _ in range(3):
        await repo.create(
            UserActivityEntry(
                user_id=user.id,
                activity_type=ActivityType.PROFILE_UPDATED,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )

    recent = await repo.list_recent_for_user(user.id, limit=2)

    assert len(recent) == 2


async def test_tag_repository_lookups(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = UserTagRepository(db_session)
    tag = await repo.create(
        UserTag(user_id=user.id, label="vip", organization_id=DEFAULT_ORGANIZATION_ID)
    )

    by_label = await repo.get_by_label(user.id, "vip")
    assert by_label is not None
    assert by_label.id == tag.id
    assert await repo.get_by_label(user.id, "missing") is None
    assert len(await repo.list_for_user(user.id)) == 1
    assert tag in await repo.list_users_for_label("vip")


async def test_note_repository_list_for_user(db_session: AsyncSession) -> None:
    subject = await _make_user(db_session)
    author = await _make_user(db_session)
    repo = UserNoteRepository(db_session)
    await repo.create(
        UserNote(
            user_id=subject.id,
            author_id=author.id,
            body="note",
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )

    listed = await repo.list_for_user(subject.id)

    assert len(listed) == 1


async def test_invitation_status_enum_roundtrip(db_session: AsyncSession) -> None:
    """Sanity check the enum-typed status column round-trips through Postgres."""
    inviter = await _make_user(db_session)
    repo = UserInvitationRepository(db_session)
    invitation = await repo.create(
        UserInvitation(
            email="x@example.com",
            invited_by=inviter.id,
            token_hash="hash-x",
            status=InvitationStatus.PENDING,
            expires_at=datetime.now(UTC) + timedelta(days=1),
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )

    assert str(invitation.status) == "pending"
