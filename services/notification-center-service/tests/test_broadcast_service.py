"""BroadcastService: fan-out to an explicit recipient list, a subscription
topic, or both.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import (
    AnnouncementScope,
    BroadcastStatus,
    NotificationChannelKind,
    SubscriptionKind,
)
from app.services.broadcast import BroadcastService

pytestmark = pytest.mark.asyncio


class TestBroadcast:
    async def test_broadcast_creates_one_notification_per_explicit_recipient(
        self, broadcast_service: BroadcastService, notifications_repo, organization_id
    ) -> None:
        broadcast = await broadcast_service.broadcast(
            organization_id,
            body="Heads up.",
            recipient_user_ids=["alice", "bob"],
            channel=NotificationChannelKind.IN_APP,
        )
        assert broadcast.total_recipients == 2
        found = await notifications_repo.list_by_correlation(organization_id, str(broadcast.id))
        assert {one.user_id for one in found} == {"alice", "bob"}

    async def test_broadcast_dedupes_a_recipient_in_both_the_explicit_list_and_the_topic(
        self,
        broadcast_service: BroadcastService,
        subscription_service,
        notifications_repo,
        organization_id,
    ) -> None:
        await subscription_service.subscribe(
            organization_id, "alice", SubscriptionKind.TOPIC, "updates"
        )
        broadcast = await broadcast_service.broadcast(
            organization_id,
            body="Update available.",
            recipient_user_ids=["alice", "bob"],
            topic="updates",
            channel=NotificationChannelKind.IN_APP,
        )
        assert broadcast.total_recipients == 2
        found = await notifications_repo.list_by_correlation(organization_id, str(broadcast.id))
        assert len(found) == 2
        assert {one.user_id for one in found} == {"alice", "bob"}

    async def test_broadcast_fans_out_to_every_topic_subscriber_with_no_explicit_list(
        self,
        broadcast_service: BroadcastService,
        subscription_service,
        notifications_repo,
        organization_id,
    ) -> None:
        await subscription_service.subscribe(
            organization_id, "carol", SubscriptionKind.TOPIC, "outages"
        )
        await subscription_service.subscribe(
            organization_id, "dave", SubscriptionKind.TOPIC, "outages"
        )
        broadcast = await broadcast_service.broadcast(
            organization_id,
            body="Outage resolved.",
            topic="outages",
            channel=NotificationChannelKind.IN_APP,
        )
        assert broadcast.total_recipients == 2
        found = await notifications_repo.list_by_correlation(organization_id, str(broadcast.id))
        assert {one.user_id for one in found} == {"carol", "dave"}

    async def test_broadcast_with_no_recipients_completes_with_zero_counts(
        self, broadcast_service: BroadcastService, organization_id
    ) -> None:
        broadcast = await broadcast_service.broadcast(organization_id, body="Nobody home.")
        assert broadcast.total_recipients == 0
        assert broadcast.sent_count == 0
        assert broadcast.failed_count == 0
        assert broadcast.status == BroadcastStatus.COMPLETED
        assert broadcast.completed_at is not None

    async def test_broadcast_reflects_successful_deliveries_in_sent_count(
        self, broadcast_service: BroadcastService, organization_id
    ) -> None:
        broadcast = await broadcast_service.broadcast(
            organization_id,
            body="All good.",
            recipient_user_ids=["erin", "frank"],
            channel=NotificationChannelKind.IN_APP,
        )
        assert broadcast.sent_count == 2
        assert broadcast.failed_count == 0
        assert broadcast.status == BroadcastStatus.COMPLETED

    async def test_broadcast_reflects_failed_deliveries_in_failed_count(
        self, broadcast_service: BroadcastService, organization_id
    ) -> None:
        # EMAIL is org-enabled by this service's own always-on rule but is
        # never registered in the notification_manager fixture, so it
        # genuinely fails at the shared_core channel-dispatch level --
        # exercising the broadcast's own failed_count branch for real.
        broadcast = await broadcast_service.broadcast(
            organization_id,
            body="This will not reach anyone.",
            recipient_user_ids=["nolan"],
            channel=NotificationChannelKind.EMAIL,
        )
        assert broadcast.sent_count == 0
        assert broadcast.failed_count == 1
        assert broadcast.status == BroadcastStatus.COMPLETED

    async def test_broadcast_stores_the_correlation_id_shared_by_every_notification(
        self, broadcast_service: BroadcastService, notifications_repo, organization_id
    ) -> None:
        broadcast = await broadcast_service.broadcast(
            organization_id,
            body="Correlated.",
            recipient_user_ids=["gina"],
            channel=NotificationChannelKind.IN_APP,
        )
        found = await notifications_repo.list_by_correlation(organization_id, str(broadcast.id))
        assert len(found) == 1
        assert found[0].correlation_id == str(broadcast.id)

    async def test_broadcast_stores_topic_and_announcement_id(
        self, broadcast_service: BroadcastService, announcement_service, organization_id
    ) -> None:
        announcement = await announcement_service.create(
            organization_id, scope=AnnouncementScope.SYSTEM, title="Release", body="Notes."
        )
        broadcast = await broadcast_service.broadcast(
            organization_id,
            body="Linked to an announcement.",
            recipient_user_ids=["harold"],
            topic="release-notes",
            announcement_id=announcement.id,
            channel=NotificationChannelKind.IN_APP,
        )
        assert broadcast.topic == "release-notes"
        assert broadcast.announcement_id == announcement.id

    async def test_broadcast_with_a_non_uuid_initiated_by_does_not_crash(
        self, broadcast_service: BroadcastService, organization_id
    ) -> None:
        # Regression test: initiated_by used to be forwarded as the
        # per-recipient notification's own actor_id, and NotificationService
        # .create() does `UUID(actor_id)` on it -- a plain human/system
        # actor label like "admin" is not a UUID and crashed there. It is
        # now only ever stored on the NotificationBroadcast row itself.
        broadcast = await broadcast_service.broadcast(
            organization_id,
            body="Started by an operator.",
            recipient_user_ids=["ivy"],
            initiated_by="admin",
            channel=NotificationChannelKind.IN_APP,
        )
        assert broadcast.initiated_by == "admin"
        assert broadcast.sent_count == 1


class TestGetAndList:
    async def test_get_returns_the_broadcast(
        self, broadcast_service: BroadcastService, organization_id
    ) -> None:
        created = await broadcast_service.broadcast(
            organization_id, body="Fetch me.", recipient_user_ids=["jack"]
        )
        found = await broadcast_service.get(organization_id, created.id)
        assert found.id == created.id

    async def test_get_raises_not_found_for_a_missing_broadcast(
        self, broadcast_service: BroadcastService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await broadcast_service.get(organization_id, uuid4())

    async def test_get_is_scoped_to_its_organization(
        self, broadcast_service: BroadcastService, organization_id
    ) -> None:
        created = await broadcast_service.broadcast(
            organization_id, body="Scoped.", recipient_user_ids=["kate"]
        )
        with pytest.raises(NotFoundError):
            await broadcast_service.get(uuid4(), created.id)

    async def test_list_broadcasts_filters_by_status(
        self, broadcast_service: BroadcastService, organization_id
    ) -> None:
        completed = await broadcast_service.broadcast(
            organization_id, body="Done.", recipient_user_ids=["leo"]
        )
        found = await broadcast_service.list_broadcasts(
            organization_id, status=BroadcastStatus.COMPLETED
        )
        assert completed.id in {one.id for one in found}

        none_pending = await broadcast_service.list_broadcasts(
            organization_id, status=BroadcastStatus.PENDING
        )
        assert none_pending == []
