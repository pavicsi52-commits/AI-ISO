"""AnnouncementService: creation, publication, and expiry.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError
from tests.conftest import ago, soon

from app.models.enums import AnnouncementScope, AnnouncementStatus
from app.services.announcement import AnnouncementService

pytestmark = pytest.mark.asyncio


class TestCreate:
    async def test_create_succeeds_with_no_dates(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        announcement = await announcement_service.create(
            organization_id, scope=AnnouncementScope.SYSTEM, title="Maintenance", body="Tonight."
        )
        assert announcement.status == AnnouncementStatus.DRAFT
        assert announcement.starts_at is None
        assert announcement.expires_at is None

    async def test_create_succeeds_with_only_starts_at(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        announcement = await announcement_service.create(
            organization_id,
            scope=AnnouncementScope.ORGANIZATION,
            title="Rollout",
            body="Starting soon.",
            starts_at=soon(hours=2),
        )
        assert announcement.starts_at is not None
        assert announcement.expires_at is None

    async def test_create_succeeds_with_only_expires_at_even_if_in_the_past(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        # A nonsensical combination alone (an already-past expires_at with
        # no starts_at) still doesn't raise -- only the *pairing* is
        # validated, per this service's own docstring.
        announcement = await announcement_service.create(
            organization_id,
            scope=AnnouncementScope.SYSTEM,
            title="Old notice",
            body="Body.",
            expires_at=ago(hours=1),
        )
        assert announcement.expires_at is not None

    async def test_create_succeeds_when_expires_at_is_after_starts_at(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        announcement = await announcement_service.create(
            organization_id,
            scope=AnnouncementScope.SYSTEM,
            title="Window",
            body="Body.",
            starts_at=soon(hours=1),
            expires_at=soon(hours=2),
        )
        assert announcement.starts_at < announcement.expires_at

    async def test_create_raises_validation_error_when_expires_at_is_before_starts_at(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        with pytest.raises(ValidationError):
            await announcement_service.create(
                organization_id,
                scope=AnnouncementScope.SYSTEM,
                title="Bad window",
                body="Body.",
                starts_at=soon(hours=2),
                expires_at=soon(hours=1),
            )

    async def test_create_raises_validation_error_when_expires_at_equals_starts_at(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        moment = soon(hours=1)
        with pytest.raises(ValidationError):
            await announcement_service.create(
                organization_id,
                scope=AnnouncementScope.SYSTEM,
                title="Zero-width window",
                body="Body.",
                starts_at=moment,
                expires_at=moment,
            )

    async def test_create_sets_created_by_when_actor_id_is_given(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        actor_id = str(uuid4())
        announcement = await announcement_service.create(
            organization_id,
            scope=AnnouncementScope.SYSTEM,
            title="Attributed",
            body="Body.",
            actor_id=actor_id,
        )
        assert str(announcement.created_by) == actor_id

    async def test_create_stores_audience_and_is_pinned(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        announcement = await announcement_service.create(
            organization_id,
            scope=AnnouncementScope.PROJECT,
            title="Pinned",
            body="Body.",
            is_pinned=True,
            audience={"projects": ["proj-1"]},
        )
        assert announcement.is_pinned is True
        assert announcement.audience == {"projects": ["proj-1"]}


class TestGetAndList:
    async def test_get_returns_the_announcement(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        created = await announcement_service.create(
            organization_id, scope=AnnouncementScope.SYSTEM, title="Get me", body="Body."
        )
        found = await announcement_service.get(organization_id, created.id)
        assert found.id == created.id

    async def test_get_raises_not_found_for_a_missing_announcement(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await announcement_service.get(organization_id, uuid4())

    async def test_get_is_scoped_to_its_organization(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        created = await announcement_service.create(
            organization_id, scope=AnnouncementScope.SYSTEM, title="Scoped", body="Body."
        )
        with pytest.raises(NotFoundError):
            await announcement_service.get(uuid4(), created.id)

    async def test_list_announcements_filters_by_status(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        draft = await announcement_service.create(
            organization_id, scope=AnnouncementScope.SYSTEM, title="Draft one", body="Body."
        )
        published_source = await announcement_service.create(
            organization_id, scope=AnnouncementScope.SYSTEM, title="Published one", body="Body."
        )
        await announcement_service.publish(organization_id, published_source.id)

        drafts = await announcement_service.list_announcements(
            organization_id, status=AnnouncementStatus.DRAFT
        )
        published = await announcement_service.list_announcements(
            organization_id, status=AnnouncementStatus.PUBLISHED
        )
        assert {one.id for one in drafts} == {draft.id}
        assert {one.id for one in published} == {published_source.id}


class TestUpdate:
    async def test_update_changes_editable_fields(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        created = await announcement_service.create(
            organization_id, scope=AnnouncementScope.SYSTEM, title="Old title", body="Old body."
        )
        updated = await announcement_service.update(
            organization_id, created.id, title="New title", body="New body.", is_pinned=True
        )
        assert updated.title == "New title"
        assert updated.body == "New body."
        assert updated.is_pinned is True

    async def test_update_ignores_fields_outside_the_editable_set(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        created = await announcement_service.create(
            organization_id, scope=AnnouncementScope.SYSTEM, title="Untouchable status", body="Body."
        )
        updated = await announcement_service.update(
            organization_id, created.id, status=AnnouncementStatus.PUBLISHED
        )
        assert updated.status == AnnouncementStatus.DRAFT

    async def test_update_ignores_none_values(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        created = await announcement_service.create(
            organization_id, scope=AnnouncementScope.SYSTEM, title="Original", body="Original body."
        )
        updated = await announcement_service.update(
            organization_id, created.id, title=None, body="Updated body."
        )
        assert updated.title == "Original"
        assert updated.body == "Updated body."

    async def test_update_sets_updated_by(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        created = await announcement_service.create(
            organization_id, scope=AnnouncementScope.SYSTEM, title="Title", body="Body."
        )
        actor_id = str(uuid4())
        updated = await announcement_service.update(
            organization_id, created.id, title="Title v2", actor_id=actor_id
        )
        assert str(updated.updated_by) == actor_id


class TestPublish:
    async def test_publish_sets_published_at_and_publishes_the_event(
        self, announcement_service: AnnouncementService, organization_id, publisher
    ) -> None:
        created = await announcement_service.create(
            organization_id, scope=AnnouncementScope.SYSTEM, title="Go live", body="Body."
        )
        published = await announcement_service.publish(organization_id, created.id)
        assert published.status == AnnouncementStatus.PUBLISHED
        assert published.published_at is not None
        assert "AnnouncementPublished" in publisher.names

    async def test_publish_sets_updated_by(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        created = await announcement_service.create(
            organization_id, scope=AnnouncementScope.SYSTEM, title="Go live", body="Body."
        )
        actor_id = str(uuid4())
        published = await announcement_service.publish(organization_id, created.id, actor_id=actor_id)
        assert str(published.updated_by) == actor_id

    async def test_publish_raises_validation_error_if_already_published(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        created = await announcement_service.create(
            organization_id, scope=AnnouncementScope.SYSTEM, title="Twice", body="Body."
        )
        await announcement_service.publish(organization_id, created.id)
        with pytest.raises(ValidationError):
            await announcement_service.publish(organization_id, created.id)

    async def test_publish_without_a_publisher_does_not_raise(
        self, announcements_repo, organization_id
    ) -> None:
        service = AnnouncementService(announcements_repo)
        created = await service.create(
            organization_id, scope=AnnouncementScope.SYSTEM, title="No publisher", body="Body."
        )
        published = await service.publish(organization_id, created.id)
        assert published.status == AnnouncementStatus.PUBLISHED


class TestArchive:
    async def test_archive_sets_status_and_updated_by(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        created = await announcement_service.create(
            organization_id, scope=AnnouncementScope.SYSTEM, title="Retire me", body="Body."
        )
        await announcement_service.publish(organization_id, created.id)
        actor_id = str(uuid4())
        archived = await announcement_service.archive(organization_id, created.id, actor_id=actor_id)
        assert archived.status == AnnouncementStatus.ARCHIVED
        assert str(archived.updated_by) == actor_id


class TestExpireDue:
    async def test_expires_published_and_overdue_announcements(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        created = await announcement_service.create(
            organization_id,
            scope=AnnouncementScope.SYSTEM,
            title="Overdue",
            body="Body.",
            expires_at=ago(hours=1),
        )
        await announcement_service.publish(organization_id, created.id)

        count = await announcement_service.expire_due(now=ago(hours=0))
        assert count == 1
        reloaded = await announcement_service.get(organization_id, created.id)
        assert reloaded.status == AnnouncementStatus.EXPIRED

    async def test_ignores_a_draft_announcement_even_if_overdue(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        created = await announcement_service.create(
            organization_id,
            scope=AnnouncementScope.SYSTEM,
            title="Never published",
            body="Body.",
            expires_at=ago(hours=1),
        )
        count = await announcement_service.expire_due(now=ago(hours=0))
        assert count == 0
        reloaded = await announcement_service.get(organization_id, created.id)
        assert reloaded.status == AnnouncementStatus.DRAFT

    async def test_ignores_an_archived_announcement_even_if_overdue(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        created = await announcement_service.create(
            organization_id,
            scope=AnnouncementScope.SYSTEM,
            title="Already archived",
            body="Body.",
            expires_at=ago(hours=1),
        )
        await announcement_service.publish(organization_id, created.id)
        await announcement_service.archive(organization_id, created.id)

        count = await announcement_service.expire_due(now=ago(hours=0))
        assert count == 0
        reloaded = await announcement_service.get(organization_id, created.id)
        assert reloaded.status == AnnouncementStatus.ARCHIVED

    async def test_ignores_a_published_announcement_not_yet_due(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        created = await announcement_service.create(
            organization_id,
            scope=AnnouncementScope.SYSTEM,
            title="Not due yet",
            body="Body.",
            expires_at=soon(hours=5),
        )
        await announcement_service.publish(organization_id, created.id)

        count = await announcement_service.expire_due(now=ago(hours=0))
        assert count == 0
        reloaded = await announcement_service.get(organization_id, created.id)
        assert reloaded.status == AnnouncementStatus.PUBLISHED

    async def test_ignores_a_published_announcement_with_no_expiry(
        self, announcement_service: AnnouncementService, organization_id
    ) -> None:
        created = await announcement_service.create(
            organization_id, scope=AnnouncementScope.SYSTEM, title="Never expires", body="Body."
        )
        await announcement_service.publish(organization_id, created.id)

        count = await announcement_service.expire_due(now=soon(hours=1000))
        assert count == 0
        reloaded = await announcement_service.get(organization_id, created.id)
        assert reloaded.status == AnnouncementStatus.PUBLISHED
