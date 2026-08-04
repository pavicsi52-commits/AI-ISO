"""NotificationService: creation, reads, acknowledgement, and cancellation.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.models.enums import (
    NotificationCategory,
    NotificationPriority,
    NotificationStatus,
)
from app.services.notification import NotificationService

pytestmark = pytest.mark.asyncio


class TestCreate:
    async def test_creates_with_status_created(
        self, notification_service: NotificationService, organization_id
    ) -> None:
        created = await notification_service.create(
            organization_id,
            user_id="user-1",
            category=NotificationCategory.INFORMATION,
            source_service="test-suite",
            body="Something happened.",
        )
        assert created.status == NotificationStatus.CREATED
        assert created.user_id == "user-1"
        assert created.body == "Something happened."

    async def test_publishes_notification_created_event(
        self, notification_service: NotificationService, organization_id, publisher
    ) -> None:
        await notification_service.create(
            organization_id,
            user_id="user-1",
            category=NotificationCategory.ALERT,
            source_service="test-suite",
            body="Alert body.",
        )
        assert publisher.names == ["NotificationCreated"]

    async def test_uses_default_field_values(
        self, notification_service: NotificationService, organization_id
    ) -> None:
        created = await notification_service.create(
            organization_id,
            user_id="user-1",
            category=NotificationCategory.INFORMATION,
            source_service="test-suite",
            body="Default fields.",
        )
        assert created.priority == NotificationPriority.NORMAL
        assert created.template_variables == {}
        assert created.tags == []
        assert created.notification_metadata == {}
        assert created.created_by is None
        assert created.subject is None
        assert created.template_id is None

    async def test_does_not_publish_without_an_injected_publisher(
        self, notifications_repo, organization_id
    ) -> None:
        # `publish_event` is optional -- a service built without one (unlike
        # the `notification_service` fixture, which always wires the
        # recording `publisher`) must still create successfully.
        bare_service = NotificationService(notifications_repo)
        created = await bare_service.create(
            organization_id,
            user_id="user-1",
            category=NotificationCategory.INFORMATION,
            source_service="test-suite",
            body="No publisher wired.",
        )
        assert created.status == NotificationStatus.CREATED

    async def test_sets_provided_optional_fields(
        self, notification_service: NotificationService, organization_id
    ) -> None:
        actor_id = uuid4()
        created = await notification_service.create(
            organization_id,
            user_id="user-1",
            category=NotificationCategory.INFORMATION,
            source_service="test-suite",
            body="With extras.",
            subject="A subject",
            priority=NotificationPriority.HIGH,
            template_variables={"name": "Ada"},
            tags=["a", "b"],
            metadata={"key": "value"},
            actor_id=str(actor_id),
        )
        assert created.subject == "A subject"
        assert created.priority == NotificationPriority.HIGH
        assert created.template_variables == {"name": "Ada"}
        assert created.tags == ["a", "b"]
        assert created.notification_metadata == {"key": "value"}
        assert created.created_by == actor_id


class TestGet:
    async def test_raises_not_found_for_a_missing_notification(
        self, notification_service: NotificationService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await notification_service.get(organization_id, uuid4())

    async def test_raises_not_found_for_a_cross_org_id(
        self, notification_service: NotificationService, organization_id, make_notification
    ) -> None:
        created = await make_notification(user_id="user-1")
        with pytest.raises(NotFoundError):
            await notification_service.get(uuid4(), created.id)

    async def test_returns_the_notification_within_its_own_org(
        self, notification_service: NotificationService, organization_id, make_notification
    ) -> None:
        created = await make_notification(user_id="user-1")
        fetched = await notification_service.get(organization_id, created.id)
        assert fetched.id == created.id


class TestListNotifications:
    async def test_returns_notifications_in_this_org(
        self, notification_service: NotificationService, organization_id, make_notification
    ) -> None:
        created = await make_notification(user_id="user-1")
        found = await notification_service.list_notifications(organization_id)
        ids = {one.id for one in found}
        assert created.id in ids

    async def test_filters_by_user_id(
        self, notification_service: NotificationService, organization_id, make_notification
    ) -> None:
        await make_notification(user_id="user-1")
        await make_notification(user_id="user-2")
        found = await notification_service.list_notifications(organization_id, user_id="user-1")
        assert all(one.user_id == "user-1" for one in found)
        assert len(found) == 1


class TestMarkRead:
    async def test_sets_read_at_and_status_read(
        self, notification_service: NotificationService, organization_id, make_notification
    ) -> None:
        created = await make_notification(user_id="user-1")
        updated = await notification_service.mark_read(organization_id, created.id)
        assert updated.read_at is not None
        assert updated.status == NotificationStatus.READ

    async def test_is_idempotent_on_a_second_call(
        self, notification_service: NotificationService, organization_id, make_notification
    ) -> None:
        created = await make_notification(user_id="user-1")
        first = await notification_service.mark_read(organization_id, created.id)
        first_read_at = first.read_at
        second = await notification_service.mark_read(organization_id, created.id)
        assert second.read_at == first_read_at
        assert second.status == NotificationStatus.READ

    async def test_does_not_downgrade_from_acknowledged(
        self, notification_service: NotificationService, organization_id, make_notification
    ) -> None:
        created = await make_notification(user_id="user-1")
        await notification_service.acknowledge(organization_id, created.id)
        updated = await notification_service.mark_read(organization_id, created.id)
        assert updated.status == NotificationStatus.ACKNOWLEDGED

    async def test_does_not_downgrade_when_already_acknowledged_with_no_read_at(
        self,
        notification_service: NotificationService,
        organization_id,
        make_notification,
        notifications_repo,
    ) -> None:
        # A state unreachable through the service's own public API (`acknowledge`
        # always sets `read_at` when it sets `ACKNOWLEDGED`) but exercised here
        # directly against the repository to cover the guard itself: even a
        # notification that reaches `mark_read` with `read_at` still unset must
        # not be downgraded away from `ACKNOWLEDGED`.
        created = await make_notification(user_id="user-1")
        created.status = NotificationStatus.ACKNOWLEDGED
        await notifications_repo.update(created)

        updated = await notification_service.mark_read(organization_id, created.id)
        assert updated.read_at is not None
        assert updated.status == NotificationStatus.ACKNOWLEDGED


class TestAcknowledge:
    async def test_sets_both_timestamps_when_never_read(
        self, notification_service: NotificationService, organization_id, make_notification
    ) -> None:
        created = await make_notification(user_id="user-1")
        updated = await notification_service.acknowledge(organization_id, created.id)
        assert updated.read_at is not None
        assert updated.acknowledged_at is not None
        assert updated.status == NotificationStatus.ACKNOWLEDGED

    async def test_does_not_overwrite_an_existing_read_at(
        self, notification_service: NotificationService, organization_id, make_notification
    ) -> None:
        created = await make_notification(user_id="user-1")
        read = await notification_service.mark_read(organization_id, created.id)
        original_read_at = read.read_at
        acknowledged = await notification_service.acknowledge(organization_id, created.id)
        assert acknowledged.read_at == original_read_at
        assert acknowledged.acknowledged_at is not None
        assert acknowledged.status == NotificationStatus.ACKNOWLEDGED


class TestCancel:
    async def test_cancels_a_fresh_created_notification(
        self, notification_service: NotificationService, organization_id, make_notification
    ) -> None:
        created = await make_notification(user_id="user-1")
        cancelled = await notification_service.cancel(organization_id, created.id)
        assert cancelled.status == NotificationStatus.CANCELLED

    async def test_raises_validation_error_when_already_acknowledged(
        self, notification_service: NotificationService, organization_id, make_notification
    ) -> None:
        created = await make_notification(user_id="user-1")
        await notification_service.acknowledge(organization_id, created.id)
        with pytest.raises(ValidationError):
            await notification_service.cancel(organization_id, created.id)


class TestDelete:
    async def test_soft_deletes_and_get_afterward_raises_not_found(
        self, notification_service: NotificationService, organization_id, make_notification
    ) -> None:
        created = await make_notification(user_id="user-1")
        await notification_service.delete(organization_id, created.id)
        with pytest.raises(NotFoundError):
            await notification_service.get(organization_id, created.id)

    async def test_accepts_an_actor_id(
        self, notification_service: NotificationService, organization_id, make_notification
    ) -> None:
        created = await make_notification(user_id="user-1")
        await notification_service.delete(organization_id, created.id, actor_id=str(uuid4()))
        with pytest.raises(NotFoundError):
            await notification_service.get(organization_id, created.id)
