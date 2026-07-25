"""Notification manager.

The primary developer-facing entry point a service actually calls,
mirroring :class:`shared_core.monitoring.manager.MonitoringManager`'s
role (Prompt 023): wires the channel registry, router, dispatcher,
preferences, subscriptions, and analytics together behind one small API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.enums.priority import Priority
from shared_core.notifications.analytics import NotificationAnalytics
from shared_core.notifications.channels import ChannelRegistry, build_notification
from shared_core.notifications.delivery import DeliveryResult, DeliveryStatus, build_delivery_result
from shared_core.notifications.dispatcher import NotificationDispatcher
from shared_core.notifications.history import HistoryStore
from shared_core.notifications.preferences import PreferencesStore
from shared_core.notifications.retry import DeadLetterStore
from shared_core.notifications.router import NotificationRouter
from shared_core.notifications.subscriptions import SubscriptionRegistry
from shared_core.notifications.tracking import TrackingRecorder


@dataclass(slots=True)
class NotificationManager:
    """Everything a service needs to send, route, and track notifications.

    ``history``/``dead_letters`` default to their own fresh, empty
    stores if not given -- but ``dispatcher`` almost always already owns
    its *own* ``HistoryStore``/``DeadLetterStore`` instances. Pass the
    *same* instances to both (as :func:`~shared_core.notifications
    .factory.create_notification_framework` does) so
    :attr:`analytics`/:attr:`dead_letters` actually reflect what
    ``dispatcher`` records, rather than silently reading an empty,
    disconnected store.
    """

    channels: ChannelRegistry
    dispatcher: NotificationDispatcher
    router: NotificationRouter
    preferences: PreferencesStore
    subscriptions: SubscriptionRegistry = field(default_factory=SubscriptionRegistry)
    history: HistoryStore = field(default_factory=HistoryStore)
    tracking: TrackingRecorder = field(default_factory=TrackingRecorder)
    dead_letters: DeadLetterStore = field(default_factory=DeadLetterStore)

    @property
    def analytics(self) -> NotificationAnalytics:
        """A fresh :class:`NotificationAnalytics` view over the current history/tracking."""
        return NotificationAnalytics(history=self.history, tracking=self.tracking)

    async def send(
        self,
        *,
        user_id: str,
        notification_type: NotificationType,
        body: str,
        channel: NotificationChannel | None = None,
        priority: Priority = Priority.NORMAL,
        **fields: Any,
    ) -> DeliveryResult:
        """Send one notification to *user_id*.

        Routes through :attr:`router` first: with an explicit *channel*,
        delivers there only if the user's preferences allow it; with no
        *channel*, delivers over the single highest-priority channel
        from the user's preferences (``channel_priority``, or list order
        in ``preferred_channels`` with no configured priority). To reach
        more than one channel for the same notification, call
        :meth:`send` once per channel.
        """
        resolved = self.router.resolve_channels(
            user_id, notification_type=notification_type, requested_channel=channel
        )
        if not resolved:
            return build_delivery_result(
                status=DeliveryStatus.CANCELLED,
                channel=channel or NotificationChannel.EMAIL,
                error="No allowed channel for this user and notification type.",
            )
        target_channel = resolved[0]
        message = build_notification(
            channel=target_channel,
            notification_type=notification_type,
            body=body,
            priority=priority,
            user_id=user_id,
            **fields,
        )
        return await self.dispatcher.dispatch(message)

    async def broadcast(
        self,
        *,
        topic: str,
        notification_type: NotificationType,
        body: str,
        priority: Priority = Priority.NORMAL,
        **fields: Any,
    ) -> list[DeliveryResult]:
        """Send one notification to every subscriber of *topic* ("Broadcast Groups")."""
        results = []
        for user_id in self.subscriptions.subscribers_of(topic):
            results.append(
                await self.send(
                    user_id=user_id,
                    notification_type=notification_type,
                    body=body,
                    priority=priority,
                    **fields,
                )
            )
        return results


__all__ = ["NotificationManager"]
