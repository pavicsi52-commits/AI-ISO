"""Notification delivery: dispatch, retry attempts, and dead-lettering.

**This is the one place actual channel I/O happens.** Every other
service layer here only ever reads/writes this service's own tables;
:class:`DeliveryService` is the thin seam between them and
`shared_core.notifications.manager.NotificationManager`, the shared
send/route/history machinery every prior AI-IOS service already uses for
its own best-effort outbound notifications -- this service is the
platform's *central*, persisted version of the same framework.

One notification fans out into one :class:`~app.models.delivery
.NotificationDelivery` row per resolved channel; each delivery's own
retry loop is attempted through :meth:`DeliveryService._attempt`,
called both for the first attempt (from :meth:`dispatch`) and for every
later attempt (from :meth:`retry_due`, the retry sweep's own entry
point, and :meth:`retry_dead_letter`, a manual retry) -- one code path,
not three copies of the same retry-recording logic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from shared_core.exceptions.notification import NotificationError
from shared_core.notifications.delivery import DeliveryStatus as SharedDeliveryStatus
from shared_core.notifications.delivery import build_delivery_result
from shared_core.notifications.manager import NotificationManager
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import NotificationServiceSettings
from app.events.notification_events import (
    SOURCE_SERVICE,
    NotificationDeliveredEvent,
    NotificationFailedEvent,
    NotificationQueuedEvent,
    NotificationRetriedEvent,
    NotificationSentEvent,
)
from app.models.delivery import NotificationDelivery, NotificationDeliveryAttempt
from app.models.enums import (
    TERMINAL_NOTIFICATION_STATUSES,
    NotificationChannelKind,
    NotificationStatus,
    notification_category_of,
    notification_channel_kind_of,
    notification_status_of,
    to_shared_channel,
    to_shared_notification_type,
    to_shared_priority,
)
from app.models.notification import Notification
from app.models.retry import NotificationDeadLetter, NotificationRetryQueueEntry
from app.repositories.channel import NotificationChannelConfigRepository
from app.repositories.delivery import (
    NotificationDeliveryAttemptRepository,
    NotificationDeliveryRepository,
)
from app.repositories.notification import NotificationRepository
from app.repositories.preference import NotificationPreferenceRepository
from app.repositories.retry import (
    NotificationDeadLetterRepository,
    NotificationRetryQueueRepository,
)
from app.retries import engine as retries_engine
from app.routing import engine as routing_engine
from app.services.channel import ChannelConfigService
from app.services.preference import PreferenceService
from app.types import EventPublisher

_WEBHOOK_SHAPED_CHANNELS = frozenset(
    {
        NotificationChannelKind.WEBHOOK,
        NotificationChannelKind.SLACK,
        NotificationChannelKind.TEAMS,
        NotificationChannelKind.DISCORD,
        NotificationChannelKind.REST_CALLBACK,
        NotificationChannelKind.CUSTOM,
    }
)

_SUCCESS_STATUSES = frozenset({SharedDeliveryStatus.SENT, SharedDeliveryStatus.DELIVERED})


class DeliveryService:
    """Dispatches notifications, records delivery attempts, retries, and dead-letters."""

    def __init__(
        self,
        notifications: NotificationRepository,
        deliveries: NotificationDeliveryRepository,
        attempts: NotificationDeliveryAttemptRepository,
        retry_queue: NotificationRetryQueueRepository,
        dead_letters: NotificationDeadLetterRepository,
        preferences: PreferenceService,
        channels: ChannelConfigService,
        manager: NotificationManager,
        settings: NotificationServiceSettings,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._notifications = notifications
        self._deliveries = deliveries
        self._attempts = attempts
        self._retry_queue = retry_queue
        self._dead_letters = dead_letters
        self._preferences = preferences
        self._channels = channels
        self._manager = manager
        self._settings = settings
        self._publish = publish_event

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def dispatch(
        self,
        organization_id: UUID,
        notification: Notification,
        *,
        requested_channel: NotificationChannelKind | None = None,
    ) -> list[NotificationDelivery]:
        """Resolve channels for *notification* and attempt delivery over each.

        Resolution combines the recipient's own preferences
        (:mod:`app.routing.engine`) with which channels this
        organization has actually configured and enabled
        (:class:`~app.services.channel.ChannelConfigService`) -- a
        channel a user prefers but their organization has not
        configured is never attempted.
        """
        preference_row = await self._preferences.get(organization_id, notification.user_id)
        snapshot = PreferenceService.to_snapshot(preference_row)
        category = notification_category_of(notification.category)
        candidate_channels = routing_engine.resolve_channels(
            snapshot, category=category, requested_channel=requested_channel
        )
        resolved_channels = [
            channel
            for channel in candidate_channels
            if await self._channels.is_enabled(organization_id, channel)
        ]

        if not resolved_channels:
            notification.status = NotificationStatus.CANCELLED
            await self._notifications.update(notification)
            return []

        if notification.status == NotificationStatus.CREATED:
            notification.status = NotificationStatus.QUEUED
            await self._notifications.update(notification)

        deliveries: list[NotificationDelivery] = []
        for channel in resolved_channels:
            delivery = await self._deliveries.create(
                NotificationDelivery(
                    organization_id=organization_id,
                    notification_id=notification.id,
                    channel=channel,
                    status=NotificationStatus.QUEUED,
                    queued_at=datetime.now(UTC),
                )
            )
            await self._publish_event(
                NotificationQueuedEvent(
                    source_service=SOURCE_SERVICE,
                    organization_id=organization_id,
                    payload={
                        "notification_id": str(notification.id),
                        "delivery_id": str(delivery.id),
                        "channel": str(channel),
                    },
                )
            )
            deliveries.append(
                await self._attempt(organization_id, notification, delivery, attempt_number=1)
            )
        return deliveries

    async def list_for_notification(
        self, organization_id: UUID, notification_id: UUID
    ) -> list[NotificationDelivery]:
        """Every channel one notification was (or is being) delivered over."""
        return await self._deliveries.list_for_notification(organization_id, notification_id)

    async def _resolve_webhook_url(
        self, organization_id: UUID, channel: NotificationChannelKind
    ) -> str | None:
        config = await self._channels.get_config(organization_id, channel)
        if config is None:
            return None
        url = config.config.get("webhook_url")
        return str(url) if url else None

    async def _attempt(
        self,
        organization_id: UUID,
        notification: Notification,
        delivery: NotificationDelivery,
        *,
        attempt_number: int,
    ) -> NotificationDelivery:
        """Make one delivery attempt, recording it, then retry or dead-letter on failure."""
        channel = notification_channel_kind_of(delivery.channel)
        extra_fields: dict[str, Any] = {}
        if channel in _WEBHOOK_SHAPED_CHANNELS:
            webhook_url = await self._resolve_webhook_url(organization_id, channel)
            if webhook_url:
                extra_fields["metadata"] = {"webhook_url": webhook_url}

        try:
            result = await self._manager.send(
                user_id=notification.user_id,
                notification_type=to_shared_notification_type(
                    notification_category_of(notification.category)
                ),
                body=notification.body,
                channel=to_shared_channel(channel),
                priority=to_shared_priority(notification.priority),
                subject=notification.subject,
                organization_id=str(organization_id),
                **extra_fields,
            )
        except NotificationError as exc:
            result = build_delivery_result(
                status=SharedDeliveryStatus.FAILED,
                channel=to_shared_channel(channel),
                error=str(exc),
            )

        now = datetime.now(UTC)
        await self._attempts.create(
            NotificationDeliveryAttempt(
                organization_id=organization_id,
                delivery_id=delivery.id,
                attempt_number=attempt_number,
                status=notification_status_of(result.status.value),
                attempted_at=now,
                completed_at=now,
                error=result.error,
                latency_ms=result.latency_ms,
                provider_message_id=result.provider_message_id,
            )
        )
        delivery.attempts_used = attempt_number
        delivery.latency_ms = result.latency_ms
        delivery.provider_message_id = result.provider_message_id or delivery.provider_message_id

        if result.status in _SUCCESS_STATUSES:
            delivery.status = notification_status_of(result.status.value)
            delivery.sent_at = now
            if result.status == SharedDeliveryStatus.DELIVERED:
                delivery.delivered_at = now
            await self._deliveries.update(delivery)
            await self._publish_event(
                NotificationSentEvent(
                    source_service=SOURCE_SERVICE,
                    organization_id=organization_id,
                    payload={
                        "notification_id": str(notification.id),
                        "delivery_id": str(delivery.id),
                        "channel": str(channel),
                    },
                )
            )
            if result.status == SharedDeliveryStatus.DELIVERED:
                await self._publish_event(
                    NotificationDeliveredEvent(
                        source_service=SOURCE_SERVICE,
                        organization_id=organization_id,
                        payload={
                            "notification_id": str(notification.id),
                            "delivery_id": str(delivery.id),
                            "channel": str(channel),
                        },
                    )
                )
            await self._recompute_notification_status(organization_id, notification)
            return delivery

        delivery.error = result.error
        max_attempts = self._settings.default_max_attempts
        if retries_engine.should_retry(
            result, attempt_number=attempt_number, max_attempts=max_attempts
        ):
            delay = retries_engine.compute_delay_seconds(
                attempt_number,
                base_seconds=self._settings.default_base_delay_seconds,
                max_seconds=self._settings.default_max_delay_seconds,
            )
            await self._retry_queue.create(
                NotificationRetryQueueEntry(
                    organization_id=organization_id,
                    notification_id=notification.id,
                    delivery_id=delivery.id,
                    retry_count=attempt_number,
                    max_attempts=max_attempts,
                    next_retry_at=now + timedelta(seconds=delay),
                    last_error=result.error,
                )
            )
            await self._deliveries.update(delivery)
            return delivery

        delivery.status = NotificationStatus.FAILED
        delivery.failed_at = now
        await self._deliveries.update(delivery)
        await self._dead_letters.create(
            NotificationDeadLetter(
                organization_id=organization_id,
                notification_id=notification.id,
                delivery_id=delivery.id,
                channel=channel,
                attempts=attempt_number,
                last_error=result.error,
                dead_lettered_at=now,
            )
        )
        await self._publish_event(
            NotificationFailedEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={
                    "notification_id": str(notification.id),
                    "delivery_id": str(delivery.id),
                    "channel": str(channel),
                    "error": result.error,
                },
            )
        )
        await self._recompute_notification_status(organization_id, notification)
        return delivery

    async def _recompute_notification_status(
        self, organization_id: UUID, notification: Notification
    ) -> None:
        """Roll every one of a notification's own deliveries up into its own status.

        Never downgrades a status a recipient action already set
        (``READ``/``ACKNOWLEDGED``) or a caller already set
        (``CANCELLED``) -- only ever reflects delivery progress while the
        notification is still in an open, delivery-driven status.
        """
        current = notification_status_of(notification.status)
        if current in (
            NotificationStatus.READ,
            NotificationStatus.ACKNOWLEDGED,
            NotificationStatus.CANCELLED,
        ):
            return
        deliveries = await self._deliveries.list_for_notification(organization_id, notification.id)
        if not deliveries:
            return
        statuses = {notification_status_of(delivery.status) for delivery in deliveries}
        if NotificationStatus.DELIVERED in statuses:
            next_status = NotificationStatus.DELIVERED
        elif NotificationStatus.SENT in statuses:
            next_status = NotificationStatus.SENT
        elif statuses <= TERMINAL_NOTIFICATION_STATUSES:
            next_status = NotificationStatus.FAILED
        else:
            next_status = NotificationStatus.QUEUED
        if next_status != current:
            notification.status = next_status
            await self._notifications.update(notification)

    async def retry_due(self, *, now: datetime, limit: int = 500) -> int:
        """Attempt every retry-queue entry due at or before *now*, across every organization.

        The retry sweep's own entry point. Marks each entry resolved
        *before* attempting redelivery, so a sweep tick overlapping its
        own previous one never dispatches the same retry twice.
        """
        entries = await self._retry_queue.list_due(now=now, limit=limit)
        dispatched = 0
        for entry in entries:
            entry.resolved = True
            entry.resolved_at = now
            await self._retry_queue.update(entry)

            delivery = await self._deliveries.get_by_id(entry.delivery_id)
            notification = await self._notifications.get_by_id(entry.notification_id)
            if delivery is None or notification is None:
                continue

            await self._publish_event(
                NotificationRetriedEvent(
                    source_service=SOURCE_SERVICE,
                    organization_id=entry.organization_id,
                    payload={
                        "notification_id": str(notification.id),
                        "delivery_id": str(delivery.id),
                        "attempt_number": entry.retry_count + 1,
                    },
                )
            )
            await self._attempt(
                entry.organization_id, notification, delivery, attempt_number=entry.retry_count + 1
            )
            dispatched += 1
        return dispatched

    async def list_dead_letters(
        self,
        organization_id: UUID,
        *,
        resolved: bool | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[NotificationDeadLetter]:
        """Dead letters in this organization."""
        return await self._dead_letters.list_for_org(
            organization_id, resolved=resolved, limit=limit, offset=offset
        )

    async def retry_dead_letter(
        self, organization_id: UUID, dead_letter_id: UUID, *, actor_id: str | None = None
    ) -> NotificationDelivery:
        """Manually retry one dead-lettered delivery ("Manual Retry")."""
        dead_letter = await self._dead_letters.require_in_org(organization_id, dead_letter_id)
        dead_letter.resolved = True
        dead_letter.resolved_at = datetime.now(UTC)
        dead_letter.resolved_by = actor_id
        await self._dead_letters.update(dead_letter)

        delivery = await self._deliveries.require_in_org(organization_id, dead_letter.delivery_id)
        notification = await self._notifications.require_in_org(
            organization_id, dead_letter.notification_id
        )
        delivery.status = NotificationStatus.QUEUED
        await self._deliveries.update(delivery)

        await self._publish_event(
            NotificationRetriedEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={
                    "notification_id": str(notification.id),
                    "delivery_id": str(delivery.id),
                    "attempt_number": delivery.attempts_used + 1,
                    "manual": True,
                },
            )
        )
        return await self._attempt(
            organization_id, notification, delivery, attempt_number=delivery.attempts_used + 1
        )


def build_delivery_service(
    session: AsyncSession,
    notification_manager: NotificationManager,
    settings: NotificationServiceSettings,
    *,
    publish_event: EventPublisher | None = None,
) -> DeliveryService:
    """Build a :class:`DeliveryService` and every repository/service it composes.

    The one place that constructor's full wiring is spelled out --
    reused by both HTTP request handling (:mod:`app.api.deps`) and the
    background workers (:mod:`app.workers.retry_sweep`,
    :mod:`app.workers.digest_sweep`), which have no request-scoped DI
    system of their own to build it for them.
    """
    return DeliveryService(
        NotificationRepository(session),
        NotificationDeliveryRepository(session),
        NotificationDeliveryAttemptRepository(session),
        NotificationRetryQueueRepository(session),
        NotificationDeadLetterRepository(session),
        PreferenceService(NotificationPreferenceRepository(session)),
        ChannelConfigService(NotificationChannelConfigRepository(session)),
        notification_manager,
        settings,
        publish_event=publish_event,
    )


__all__ = ["DeliveryService", "build_delivery_service"]
