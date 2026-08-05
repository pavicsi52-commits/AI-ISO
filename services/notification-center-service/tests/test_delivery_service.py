"""DeliveryService: dispatch, retry attempts, and dead-lettering.

Against real PostgreSQL, a real ``shared_core`` notification manager (only
``IN_APP`` registered), in a SAVEPOINT-isolated session per test. See
``tests/conftest.py``'s own module docstring and ``notification_manager``
fixture docstring for exactly why ``IN_APP`` always succeeds and every
other channel genuinely raises ``ChannelUnavailableError``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.delivery import NotificationDelivery
from app.models.enums import (
    NotificationCategory,
    NotificationChannelKind,
    NotificationStatus,
    notification_status_of,
)
from app.models.retry import NotificationDeadLetter
from app.services.delivery import DeliveryService, build_delivery_service

pytestmark = pytest.mark.asyncio


async def _exhaust_email_retries(delivery_service, deliveries, *, start=None):
    """Advance a first-failed ``EMAIL`` delivery through every remaining
    retry (``default_max_attempts=3``) until it dead-letters.

    Each ``retry_due`` call processes whatever is due *right now*; the
    tiny configured backoff (``default_base_delay_seconds=0.01``) means a
    ``now`` a couple of seconds in the future is always due.
    """
    base = start or datetime.now(UTC)
    for offset in (1, 2):
        await delivery_service.retry_due(now=base + timedelta(seconds=offset))
    return deliveries[0]


class TestBuildDeliveryService:
    async def test_build_delivery_service_produces_a_working_service(
        self,
        db_session,
        notification_manager,
        service_settings,
        publisher,
        make_notification,
        organization_id,
    ) -> None:
        service = build_delivery_service(
            db_session, notification_manager, service_settings, publish_event=publisher
        )
        assert isinstance(service, DeliveryService)
        notification = await make_notification(user_id="user-factory")
        deliveries = await service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.IN_APP
        )
        assert len(deliveries) == 1

    async def test_dispatch_without_a_publisher_does_not_raise(
        self, db_session, notification_manager, service_settings, make_notification, organization_id
    ) -> None:
        service = build_delivery_service(db_session, notification_manager, service_settings)
        notification = await make_notification(user_id="user-no-publisher")
        deliveries = await service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.IN_APP
        )
        assert len(deliveries) == 1
        assert notification_status_of(deliveries[0].status) == NotificationStatus.DELIVERED


class TestDispatchResolution:
    async def test_dispatch_cancels_when_the_org_has_not_enabled_the_requested_channel(
        self, delivery_service, make_notification, notification_service, organization_id
    ) -> None:
        # WEBHOOK is never in the always-enabled set and no
        # NotificationChannelConfig row exists for it here -- dispatch
        # filters it out before any channel I/O is even attempted.
        notification = await make_notification(user_id="user-unconfigured")
        deliveries = await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.WEBHOOK
        )
        assert deliveries == []
        reloaded = await notification_service.get(organization_id, notification.id)
        assert notification_status_of(reloaded.status) == NotificationStatus.CANCELLED

    async def test_dispatch_cancels_when_the_user_is_unsubscribed_from_the_channel(
        self,
        delivery_service,
        make_notification,
        make_preference,
        notification_service,
        organization_id,
    ) -> None:
        await make_preference(
            user_id="user-unsub", unsubscribed_channels=[str(NotificationChannelKind.IN_APP)]
        )
        notification = await make_notification(user_id="user-unsub")
        deliveries = await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.IN_APP
        )
        assert deliveries == []
        reloaded = await notification_service.get(organization_id, notification.id)
        assert notification_status_of(reloaded.status) == NotificationStatus.CANCELLED

    async def test_dispatch_cancels_when_the_category_is_muted(
        self,
        delivery_service,
        make_notification,
        make_preference,
        notification_service,
        organization_id,
    ) -> None:
        await make_preference(
            user_id="user-muted-category",
            muted_categories=[str(NotificationCategory.INFORMATION)],
        )
        notification = await make_notification(user_id="user-muted-category")
        deliveries = await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.IN_APP
        )
        assert deliveries == []
        reloaded = await notification_service.get(organization_id, notification.id)
        assert notification_status_of(reloaded.status) == NotificationStatus.CANCELLED

    async def test_dispatch_cancels_when_the_user_is_fully_muted(
        self,
        delivery_service,
        make_notification,
        make_preference,
        notification_service,
        organization_id,
    ) -> None:
        await make_preference(user_id="user-muted", muted=True)
        notification = await make_notification(user_id="user-muted")
        deliveries = await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.IN_APP
        )
        assert deliveries == []
        reloaded = await notification_service.get(organization_id, notification.id)
        assert notification_status_of(reloaded.status) == NotificationStatus.CANCELLED


class TestDispatchSuccess:
    async def test_dispatch_to_in_app_succeeds_and_rolls_the_notification_up_to_delivered(
        self, delivery_service, make_notification, notification_service, organization_id, publisher
    ) -> None:
        notification = await make_notification(user_id="user-1")
        deliveries = await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.IN_APP
        )
        assert len(deliveries) == 1
        delivery = deliveries[0]
        assert notification_status_of(delivery.status) == NotificationStatus.DELIVERED
        assert delivery.sent_at is not None
        assert delivery.delivered_at is not None
        assert delivery.attempts_used == 1

        sent_index = publisher.names.index("NotificationSent")
        delivered_index = publisher.names.index("NotificationDelivered")
        assert sent_index < delivered_index

        reloaded = await notification_service.get(organization_id, notification.id)
        assert notification_status_of(reloaded.status) == NotificationStatus.DELIVERED

    async def test_dispatch_publishes_queued_before_attempting_delivery(
        self, delivery_service, make_notification, organization_id, publisher
    ) -> None:
        notification = await make_notification(user_id="user-queue-order")
        await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.IN_APP
        )
        queued_index = publisher.names.index("NotificationQueued")
        sent_index = publisher.names.index("NotificationSent")
        assert queued_index < sent_index

    async def test_dispatch_with_no_requested_channel_fans_out_over_every_resolvable_channel(
        self, delivery_service, make_notification, organization_id
    ) -> None:
        # The default preference row prefers [EMAIL, IN_APP]; both are
        # always org-enabled, so both resolve with no explicit channel.
        notification = await make_notification(user_id="user-fanout")
        deliveries = await delivery_service.dispatch(organization_id, notification)
        assert len(deliveries) == 2
        by_channel = {str(delivery.channel): delivery for delivery in deliveries}
        assert set(by_channel) == {
            str(NotificationChannelKind.EMAIL),
            str(NotificationChannelKind.IN_APP),
        }
        assert notification_status_of(by_channel[str(NotificationChannelKind.IN_APP)].status) == (
            NotificationStatus.DELIVERED
        )
        assert notification_status_of(by_channel[str(NotificationChannelKind.EMAIL)].status) == (
            NotificationStatus.QUEUED
        )

    async def test_dispatch_creates_exactly_one_delivery_row_per_resolved_channel(
        self, delivery_service, make_notification, deliveries_repo, organization_id
    ) -> None:
        notification = await make_notification(user_id="user-count")
        await delivery_service.dispatch(organization_id, notification)
        found = await deliveries_repo.list_for_notification(organization_id, notification.id)
        assert len(found) == 2

    async def test_list_for_notification_returns_every_channel_dispatched(
        self, delivery_service, make_notification, organization_id
    ) -> None:
        notification = await make_notification(user_id="user-list")
        await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.IN_APP
        )
        await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.EMAIL
        )
        found = await delivery_service.list_for_notification(organization_id, notification.id)
        assert len(found) == 2
        channels = {str(one.channel) for one in found}
        assert channels == {str(NotificationChannelKind.IN_APP), str(NotificationChannelKind.EMAIL)}

    async def test_dispatch_again_after_already_delivered_does_not_rebump_status(
        self, delivery_service, make_notification, notification_service, organization_id
    ) -> None:
        notification = await make_notification(user_id="user-redispatch")
        await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.IN_APP
        )
        reloaded = await notification_service.get(organization_id, notification.id)
        assert notification_status_of(reloaded.status) == NotificationStatus.DELIVERED

        # A second dispatch to a channel that will fail must not disturb
        # the already-DELIVERED status: the CREATED->QUEUED bump only
        # applies while the notification is still CREATED, and a
        # retry-pending failure never calls the recompute step at all.
        await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.EMAIL
        )
        reloaded_again = await notification_service.get(organization_id, notification.id)
        assert notification_status_of(reloaded_again.status) == NotificationStatus.DELIVERED


class TestDispatchFailureAndRetryQueue:
    async def test_first_email_failure_queues_a_retry_without_dead_lettering(
        self,
        delivery_service,
        make_notification,
        retry_queue_repo,
        dead_letters_repo,
        organization_id,
        publisher,
    ) -> None:
        before = datetime.now(UTC)
        notification = await make_notification(user_id="user-2")
        deliveries = await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.EMAIL
        )
        assert len(deliveries) == 1
        delivery = deliveries[0]
        assert notification_status_of(delivery.status) == NotificationStatus.QUEUED
        assert delivery.error is not None
        assert delivery.attempts_used == 1

        pending = await retry_queue_repo.list_for_org(organization_id, resolved=False)
        assert len(pending) == 1
        assert pending[0].resolved is False
        # The attempt's own completion time plus a non-negative backoff is
        # always at or after when this test started -- unlike comparing
        # against "now" at assertion time, this holds even at this
        # fixture's tiny (0.01s) configured backoff.
        assert pending[0].next_retry_at >= before

        dead_letters = await dead_letters_repo.list_for_org(organization_id)
        assert dead_letters == []
        assert "NotificationFailed" not in publisher.names
        assert "NotificationSent" not in publisher.names

    async def test_email_failure_exhausts_retries_and_dead_letters(
        self,
        delivery_service,
        make_notification,
        notification_service,
        deliveries_repo,
        organization_id,
        publisher,
    ) -> None:
        notification = await make_notification(user_id="user-3")
        deliveries = await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.EMAIL
        )
        delivery = await _exhaust_email_retries(delivery_service, deliveries)

        reloaded_delivery = await deliveries_repo.require_in_org(organization_id, delivery.id)
        assert notification_status_of(reloaded_delivery.status) == NotificationStatus.FAILED
        assert reloaded_delivery.failed_at is not None

        dead_letters = await delivery_service.list_dead_letters(organization_id)
        assert len(dead_letters) == 1
        assert dead_letters[0].delivery_id == delivery.id
        assert dead_letters[0].attempts == 3

        reloaded_notification = await notification_service.get(organization_id, notification.id)
        assert notification_status_of(reloaded_notification.status) == NotificationStatus.FAILED
        assert "NotificationFailed" in publisher.names

    async def test_dispatch_to_a_configured_webhook_channel_still_fails_unregistered(
        self, delivery_service, channel_service, make_notification, organization_id
    ) -> None:
        await channel_service.set_config(
            organization_id,
            NotificationChannelKind.WEBHOOK,
            enabled=True,
            config={"webhook_url": "https://example.com/hook"},
        )
        notification = await make_notification(user_id="user-webhook-with-url")
        deliveries = await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.WEBHOOK
        )
        assert len(deliveries) == 1
        assert notification_status_of(deliveries[0].status) == NotificationStatus.QUEUED

    async def test_dispatch_to_a_webhook_shaped_channel_with_no_configured_url_still_attempts(
        self, delivery_service, channel_service, make_notification, organization_id
    ) -> None:
        await channel_service.set_config(
            organization_id, NotificationChannelKind.SLACK, enabled=True, config={}
        )
        notification = await make_notification(user_id="user-webhook-no-url")
        deliveries = await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.SLACK
        )
        assert len(deliveries) == 1
        assert notification_status_of(deliveries[0].status) == NotificationStatus.QUEUED


class TestRetryDue:
    async def test_retry_due_marks_an_entry_resolved_before_reattempting(
        self, delivery_service, make_notification, retry_queue_repo, organization_id
    ) -> None:
        notification = await make_notification(user_id="user-4")
        await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.EMAIL
        )
        # Fast-forward straight to the exhausting attempt (retry_count=2 ->
        # next attempt is number 3, meeting default_max_attempts=3) so the
        # sweep's own reattempt dead-letters instead of enqueuing another
        # retry -- at this fixture's tiny backoff, a freshly enqueued retry
        # could itself already be "due" by a second call, which would be a
        # red herring, not evidence of the same entry being double-processed.
        entry = (await retry_queue_repo.list_for_org(organization_id, resolved=False))[0]
        entry.retry_count = 2
        await retry_queue_repo.update(entry)

        due_time = datetime.now(UTC) + timedelta(seconds=1)
        first = await delivery_service.retry_due(now=due_time)
        assert first == 1
        second = await delivery_service.retry_due(now=due_time)
        assert second == 0

    async def test_retry_due_processes_entries_across_every_organization(
        self, delivery_service, notification_service, organization_id
    ) -> None:
        other_org = uuid4()
        notification_a = await notification_service.create(
            organization_id,
            user_id="org-a-user",
            category=NotificationCategory.INFORMATION,
            body="For org A.",
            source_service="test-suite",
        )
        notification_b = await notification_service.create(
            other_org,
            user_id="org-b-user",
            category=NotificationCategory.INFORMATION,
            body="For org B.",
            source_service="test-suite",
        )
        await delivery_service.dispatch(
            organization_id, notification_a, requested_channel=NotificationChannelKind.EMAIL
        )
        await delivery_service.dispatch(
            other_org, notification_b, requested_channel=NotificationChannelKind.EMAIL
        )
        processed = await delivery_service.retry_due(now=datetime.now(UTC) + timedelta(seconds=1))
        assert processed == 2

    async def test_retry_due_respects_the_limit(
        self, delivery_service, make_notification, retry_queue_repo, organization_id
    ) -> None:
        first_notification = await make_notification(user_id="user-limit-1")
        second_notification = await make_notification(user_id="user-limit-2")
        await delivery_service.dispatch(
            organization_id, first_notification, requested_channel=NotificationChannelKind.EMAIL
        )
        await delivery_service.dispatch(
            organization_id, second_notification, requested_channel=NotificationChannelKind.EMAIL
        )
        # Force both entries to their exhausting attempt so neither
        # reattempt requeues another retry that could confound the count.
        for entry in await retry_queue_repo.list_for_org(organization_id, resolved=False):
            entry.retry_count = 2
            await retry_queue_repo.update(entry)

        due_time = datetime.now(UTC) + timedelta(seconds=1)
        first_pass = await delivery_service.retry_due(now=due_time, limit=1)
        assert first_pass == 1
        second_pass = await delivery_service.retry_due(now=due_time, limit=500)
        assert second_pass == 1

    async def test_retry_due_skips_and_still_resolves_entries_whose_delivery_was_removed(
        self,
        delivery_service,
        make_notification,
        deliveries_repo,
        retry_queue_repo,
        organization_id,
    ) -> None:
        # A retry-queue row's delivery_id/notification_id are real foreign
        # keys, so simulating "no longer exists" (the get_by_id branch
        # DeliveryService.retry_due guards with `continue`) means
        # soft-deleting a real delivery rather than pointing at a
        # never-existed id -- get_by_id's default select excludes
        # soft-deleted rows exactly like a hard-deleted one would.
        notification = await make_notification(user_id="user-orphan")
        deliveries = await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.EMAIL
        )
        delivery = deliveries[0]
        entry = (await retry_queue_repo.list_for_org(organization_id, resolved=False))[0]
        await deliveries_repo.delete(delivery.id)

        processed = await delivery_service.retry_due(now=datetime.now(UTC) + timedelta(seconds=1))
        assert processed == 0
        reloaded = await retry_queue_repo.require_in_org(organization_id, entry.id)
        assert reloaded.resolved is True

    async def test_retry_due_publishes_retried_before_the_reattempt_outcome(
        self, delivery_service, make_notification, organization_id, publisher
    ) -> None:
        notification = await make_notification(user_id="user-5")
        deliveries = await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.EMAIL
        )
        await _exhaust_email_retries(delivery_service, deliveries)

        names = publisher.names
        retried_indices = [
            index for index, name in enumerate(names) if name == "NotificationRetried"
        ]
        failed_index = names.index("NotificationFailed")
        assert len(retried_indices) == 2
        assert retried_indices[-1] < failed_index


class TestRetryDeadLetter:
    async def test_retry_dead_letter_raises_not_found_for_an_unknown_dead_letter(
        self, delivery_service, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await delivery_service.retry_dead_letter(organization_id, uuid4())

    async def test_retry_dead_letter_reopens_and_successfully_redelivers(
        self,
        delivery_service,
        make_notification,
        deliveries_repo,
        dead_letters_repo,
        notification_service,
        organization_id,
        publisher,
    ) -> None:
        notification = await make_notification(user_id="user-manual-retry-success")
        delivery = await deliveries_repo.create(
            NotificationDelivery(
                organization_id=organization_id,
                notification_id=notification.id,
                channel=NotificationChannelKind.IN_APP,
                status=NotificationStatus.FAILED,
                queued_at=datetime.now(UTC),
                failed_at=datetime.now(UTC),
                attempts_used=3,
            )
        )
        dead_letter = await dead_letters_repo.create(
            NotificationDeadLetter(
                organization_id=organization_id,
                notification_id=notification.id,
                delivery_id=delivery.id,
                channel=NotificationChannelKind.IN_APP,
                attempts=3,
                dead_lettered_at=datetime.now(UTC),
            )
        )

        result = await delivery_service.retry_dead_letter(
            organization_id, dead_letter.id, actor_id="ops-1"
        )

        assert notification_status_of(result.status) == NotificationStatus.DELIVERED
        reloaded_dead_letter = await dead_letters_repo.require_in_org(
            organization_id, dead_letter.id
        )
        assert reloaded_dead_letter.resolved is True
        assert reloaded_dead_letter.resolved_by == "ops-1"
        assert reloaded_dead_letter.resolved_at is not None
        assert "NotificationRetried" in publisher.names
        assert publisher.names.index("NotificationRetried") < publisher.names.index(
            "NotificationDelivered"
        )

        reloaded_notification = await notification_service.get(organization_id, notification.id)
        assert notification_status_of(reloaded_notification.status) == NotificationStatus.DELIVERED

    async def test_retry_dead_letter_still_fails_and_dead_letters_again_when_exhausted(
        self,
        delivery_service,
        make_notification,
        deliveries_repo,
        dead_letters_repo,
        organization_id,
    ) -> None:
        notification = await make_notification(user_id="user-manual-retry-fails-again")
        delivery = await deliveries_repo.create(
            NotificationDelivery(
                organization_id=organization_id,
                notification_id=notification.id,
                channel=NotificationChannelKind.EMAIL,
                status=NotificationStatus.FAILED,
                queued_at=datetime.now(UTC),
                failed_at=datetime.now(UTC),
                attempts_used=3,
            )
        )
        dead_letter = await dead_letters_repo.create(
            NotificationDeadLetter(
                organization_id=organization_id,
                notification_id=notification.id,
                delivery_id=delivery.id,
                channel=NotificationChannelKind.EMAIL,
                attempts=3,
                dead_lettered_at=datetime.now(UTC),
            )
        )

        result = await delivery_service.retry_dead_letter(
            organization_id, dead_letter.id, actor_id="ops-2"
        )

        assert notification_status_of(result.status) == NotificationStatus.FAILED
        all_dead_letters = await dead_letters_repo.list_for_org(organization_id)
        assert len(all_dead_letters) == 2
        resolved = [one for one in all_dead_letters if one.resolved]
        unresolved = [one for one in all_dead_letters if not one.resolved]
        assert len(resolved) == 1
        assert len(unresolved) == 1


class TestListDeadLetters:
    async def test_list_dead_letters_filters_by_resolved(
        self,
        delivery_service,
        make_notification,
        deliveries_repo,
        dead_letters_repo,
        organization_id,
    ) -> None:
        async def _make_delivery(user_id: str) -> NotificationDelivery:
            notification = await make_notification(user_id=user_id)
            return await deliveries_repo.create(
                NotificationDelivery(
                    organization_id=organization_id,
                    notification_id=notification.id,
                    channel=NotificationChannelKind.EMAIL,
                    status=NotificationStatus.FAILED,
                    queued_at=datetime.now(UTC),
                    failed_at=datetime.now(UTC),
                    attempts_used=3,
                )
            )

        resolved_delivery = await _make_delivery("user-dl-resolved")
        unresolved_delivery = await _make_delivery("user-dl-unresolved")
        resolved_one = await dead_letters_repo.create(
            NotificationDeadLetter(
                organization_id=organization_id,
                notification_id=resolved_delivery.notification_id,
                delivery_id=resolved_delivery.id,
                channel=NotificationChannelKind.EMAIL,
                attempts=3,
                dead_lettered_at=datetime.now(UTC),
                resolved=True,
                resolved_at=datetime.now(UTC),
            )
        )
        unresolved_one = await dead_letters_repo.create(
            NotificationDeadLetter(
                organization_id=organization_id,
                notification_id=unresolved_delivery.notification_id,
                delivery_id=unresolved_delivery.id,
                channel=NotificationChannelKind.EMAIL,
                attempts=3,
                dead_lettered_at=datetime.now(UTC),
            )
        )

        resolved = await delivery_service.list_dead_letters(organization_id, resolved=True)
        unresolved = await delivery_service.list_dead_letters(organization_id, resolved=False)
        assert {one.id for one in resolved} == {resolved_one.id}
        assert {one.id for one in unresolved} == {unresolved_one.id}


class TestRecomputeNotificationStatus:
    async def test_never_downgrades_an_acknowledged_notification(
        self, delivery_service, make_notification, notification_service, organization_id
    ) -> None:
        notification = await make_notification(user_id="user-ack")
        await notification_service.acknowledge(organization_id, notification.id)

        deliveries = await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.IN_APP
        )
        assert notification_status_of(deliveries[0].status) == NotificationStatus.DELIVERED

        reloaded = await notification_service.get(organization_id, notification.id)
        assert notification_status_of(reloaded.status) == NotificationStatus.ACKNOWLEDGED

    async def test_never_downgrades_a_cancelled_notification(
        self, delivery_service, make_notification, notification_service, organization_id
    ) -> None:
        notification = await make_notification(user_id="user-cancel")
        await notification_service.cancel(organization_id, notification.id)

        deliveries = await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.IN_APP
        )
        assert len(deliveries) == 1

        reloaded = await notification_service.get(organization_id, notification.id)
        assert notification_status_of(reloaded.status) == NotificationStatus.CANCELLED

    async def test_settles_on_sent_when_no_channel_confirmed_full_delivery(
        self,
        delivery_service,
        make_notification,
        deliveries_repo,
        dead_letters_repo,
        notification_service,
        organization_id,
    ) -> None:
        notification = await make_notification(user_id="user-sent-branch")
        await deliveries_repo.create(
            NotificationDelivery(
                organization_id=organization_id,
                notification_id=notification.id,
                channel=NotificationChannelKind.SMS,
                status=NotificationStatus.SENT,
                queued_at=datetime.now(UTC),
                sent_at=datetime.now(UTC),
            )
        )
        exhausted = await deliveries_repo.create(
            NotificationDelivery(
                organization_id=organization_id,
                notification_id=notification.id,
                channel=NotificationChannelKind.EMAIL,
                status=NotificationStatus.FAILED,
                queued_at=datetime.now(UTC),
                failed_at=datetime.now(UTC),
                attempts_used=3,
            )
        )
        dead_letter = await dead_letters_repo.create(
            NotificationDeadLetter(
                organization_id=organization_id,
                notification_id=notification.id,
                delivery_id=exhausted.id,
                channel=NotificationChannelKind.EMAIL,
                attempts=3,
                dead_lettered_at=datetime.now(UTC),
            )
        )

        await delivery_service.retry_dead_letter(organization_id, dead_letter.id, actor_id="ops")

        reloaded_notification = await notification_service.get(organization_id, notification.id)
        assert notification_status_of(reloaded_notification.status) == NotificationStatus.SENT

    async def test_recompute_is_a_no_op_once_every_channel_already_agrees(
        self, delivery_service, make_notification, notification_service, organization_id
    ) -> None:
        notification = await make_notification(user_id="user-recompute-noop")
        await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.IN_APP
        )
        reloaded_once = await notification_service.get(organization_id, notification.id)
        assert notification_status_of(reloaded_once.status) == NotificationStatus.DELIVERED

        # A second IN_APP delivery for the same notification also
        # succeeds; recompute's next_status (DELIVERED) now matches the
        # already-DELIVERED current status, so the "no change" branch --
        # distinct from the never-downgrade branch above -- runs.
        await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.IN_APP
        )
        reloaded_twice = await notification_service.get(organization_id, notification.id)
        assert notification_status_of(reloaded_twice.status) == NotificationStatus.DELIVERED

    async def test_settles_on_queued_when_another_channel_is_still_pending(
        self,
        delivery_service,
        make_notification,
        deliveries_repo,
        dead_letters_repo,
        notification_service,
        organization_id,
    ) -> None:
        notification = await make_notification(user_id="user-queued-branch")
        await deliveries_repo.create(
            NotificationDelivery(
                organization_id=organization_id,
                notification_id=notification.id,
                channel=NotificationChannelKind.SMS,
                status=NotificationStatus.QUEUED,
                queued_at=datetime.now(UTC),
            )
        )
        exhausted = await deliveries_repo.create(
            NotificationDelivery(
                organization_id=organization_id,
                notification_id=notification.id,
                channel=NotificationChannelKind.EMAIL,
                status=NotificationStatus.FAILED,
                queued_at=datetime.now(UTC),
                failed_at=datetime.now(UTC),
                attempts_used=3,
            )
        )
        dead_letter = await dead_letters_repo.create(
            NotificationDeadLetter(
                organization_id=organization_id,
                notification_id=notification.id,
                delivery_id=exhausted.id,
                channel=NotificationChannelKind.EMAIL,
                attempts=3,
                dead_lettered_at=datetime.now(UTC),
            )
        )

        await delivery_service.retry_dead_letter(organization_id, dead_letter.id, actor_id="ops")

        reloaded_notification = await notification_service.get(organization_id, notification.id)
        assert notification_status_of(reloaded_notification.status) == NotificationStatus.QUEUED
