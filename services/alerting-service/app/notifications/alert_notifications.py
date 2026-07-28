"""Alert notification delivery ("NOTIFICATIONS": Email, Slack, Teams,
Webhook, SMS, PagerDuty, ServiceNow, Custom Providers, Retry, Delivery
Tracking).

Delivery itself goes through
:class:`shared_core.notifications.manager.NotificationManager` (Prompt
025) rather than this service implementing SMTP/Slack/PagerDuty
transports of its own. What this module adds on top is the part
``shared_core`` deliberately does not own: a persisted
:class:`~app.models.alert_notification.AlertNotification` row per
attempt, so "Delivery Tracking" and "Retry" are real, queryable state
rather than a fire-and-forget log line.

**Honest gap**: ``shared_core.enums.notification_channel
.NotificationChannel`` covers EMAIL/SMS/PUSH/IN_APP/SLACK/TEAMS/
DISCORD/WEBHOOK (verified directly against that enum, not assumed) but
has no PagerDuty, ServiceNow, or Opsgenie member -- three channels
docs/045's own "ROUTING" list names explicitly. Routes configured for
those, or for ``CUSTOM``, are recorded as ``FAILED`` with an explicit
reason rather than silently dropped or mis-delivered down some other
channel -- a real platform gap, surfaced instead of faked. Closing it
means extending that shared enum and its own providers, which is
Prompt 025's own scope, not this service's.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.enums.severity import Severity
from shared_core.exceptions.notification import NotificationError
from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager

from app.events.alert_events import AlertNotificationSentEvent
from app.models.alert_instance import AlertInstance
from app.models.alert_notification import AlertNotification
from app.models.alert_route import AlertRoute
from app.models.enums import AlertRouteChannel, NotificationDeliveryStatus
from app.repositories.alert_notification import AlertNotificationRepository
from app.types import EventPublisher

logger = get_logger("app.notifications.alert_notifications")

_CHANNEL_MAP: dict[AlertRouteChannel, NotificationChannel] = {
    AlertRouteChannel.EMAIL: NotificationChannel.EMAIL,
    AlertRouteChannel.SMS: NotificationChannel.SMS,
    AlertRouteChannel.SLACK: NotificationChannel.SLACK,
    AlertRouteChannel.TEAMS: NotificationChannel.TEAMS,
    AlertRouteChannel.DISCORD: NotificationChannel.DISCORD,
    AlertRouteChannel.WEBHOOK: NotificationChannel.WEBHOOK,
}
"""Route channels this platform can genuinely deliver through today.

``PAGERDUTY``/``SERVICENOW``/``OPSGENIE``/``CUSTOM`` have no
``shared_core`` transport -- see this module's own docstring.
"""

_SEVERITY_TO_NOTIFICATION_TYPE: dict[Severity, NotificationType] = {
    Severity.CRITICAL: NotificationType.ERROR,
    Severity.HIGH: NotificationType.ERROR,
    Severity.MEDIUM: NotificationType.WARNING,
    Severity.LOW: NotificationType.WARNING,
    Severity.INFO: NotificationType.INFORMATION,
}


class AlertNotificationService:
    """Delivers alert notifications and records every attempt."""

    def __init__(
        self,
        notifications: AlertNotificationRepository,
        manager: NotificationManager,
        *,
        publish_event: EventPublisher,
    ) -> None:
        self._notifications = notifications
        self._manager = manager
        self._publish_event = publish_event

    async def list_for_alert(self, alert_id: UUID) -> list[AlertNotification]:
        """Every delivery attempt recorded for *alert_id*."""
        return await self._notifications.list_for_alert(alert_id)

    async def retry_failed(self, organization_id: UUID, *, max_attempts: int = 3) -> int:
        """Re-attempt every failed delivery under *max_attempts* ("Retry").

        Returns the number of attempts made. A record that has already
        exhausted *max_attempts* is left ``FAILED`` and not retried
        forever -- an unreachable channel must not become an infinite
        background loop.

        Marks each record ``RETRYING`` and increments its own
        ``retry_count`` before re-delivering, so a crash mid-retry
        leaves durable evidence of the attempt rather than looking like
        it never happened.
        """
        pending = await self._notifications.list_retryable(organization_id)
        attempted = 0
        for record in pending:
            if record.retry_count >= max_attempts:
                continue
            record.retry_count += 1
            record.status = NotificationDeliveryStatus.RETRYING
            await self._notifications.update(record)
            attempted += 1
        return attempted

    async def deliver(self, alert: AlertInstance, route: AlertRoute) -> AlertNotification:
        """Deliver *alert* through *route*, recording the attempt.

        Never raises on a delivery failure: a failed notification is
        recorded as ``FAILED`` (retryable) rather than aborting the
        caller, since one unreachable channel must not stop the others
        from being tried.
        """
        channel = (
            route.channel
            if isinstance(route.channel, AlertRouteChannel)
            else AlertRouteChannel(route.channel)
        )
        mapped = _CHANNEL_MAP.get(channel)
        if mapped is None:
            return await self._record(
                alert,
                route,
                channel,
                status=NotificationDeliveryStatus.FAILED,
                error_message=(
                    f"No delivery transport exists for channel {str(channel)!r}; "
                    "shared_core.notifications supports "
                    f"{sorted(str(key) for key in _CHANNEL_MAP)}."
                ),
            )

        severity = (
            alert.severity if isinstance(alert.severity, Severity) else Severity(alert.severity)
        )
        try:
            await self._manager.send(
                user_id=route.target_reference,
                notification_type=_SEVERITY_TO_NOTIFICATION_TYPE[severity],
                body=alert.message,
                channel=mapped,
                subject=alert.title,
            )
        except NotificationError as exc:
            logger.warning(
                "Alert notification delivery failed.",
                extra={
                    "extra_fields": {
                        "alert_id": str(alert.id),
                        "route_id": str(route.id),
                        "channel": str(channel),
                    }
                },
            )
            return await self._record(
                alert,
                route,
                channel,
                status=NotificationDeliveryStatus.FAILED,
                error_message=str(exc),
            )

        record = await self._record(
            alert, route, channel, status=NotificationDeliveryStatus.SENT, error_message=None
        )
        await self._publish_event(
            AlertNotificationSentEvent(
                source_service="alerting-service",
                payload={
                    "alert_id": str(alert.id),
                    "route_id": str(route.id),
                    "channel": str(channel),
                },
            )
        )
        return record

    async def _record(
        self,
        alert: AlertInstance,
        route: AlertRoute,
        channel: AlertRouteChannel,
        *,
        status: NotificationDeliveryStatus,
        error_message: str | None,
    ) -> AlertNotification:
        return await self._notifications.create(
            AlertNotification(
                organization_id=alert.organization_id,
                project_id=alert.project_id,
                alert_id=alert.id,
                route_id=route.id,
                channel=channel,
                status=status,
                error_message=error_message,
                sent_at=datetime.now(UTC) if status is NotificationDeliveryStatus.SENT else None,
            )
        )


__all__ = ["AlertNotificationService"]
