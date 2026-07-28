"""Monitoring service notifications.

Per docs/044 "NOTIFICATIONS" "Notify": Critical Health Change,
Availability Issue, Synthetic Failure, Threshold Exceeded, Capacity
Warning, Monitoring Failure. Thin wrapper over
:class:`shared_core.notifications.manager.NotificationManager`, the
same best-effort ``_send()`` pattern every prior AI-IOS service's own
notification service established -- a notification failure never
blocks the triggering operation.
"""

from __future__ import annotations

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.exceptions.notification import NotificationError
from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager

logger = get_logger("app.notifications.monitoring_notifications")


class MonitoringNotificationService:
    """Sends every monitoring-related notification this service triggers, best-effort."""

    def __init__(self, manager: NotificationManager) -> None:
        self._manager = manager

    async def _send(
        self, *, user_id: str, body: str, subject: str, notification_type: NotificationType
    ) -> None:
        try:
            await self._manager.send(
                user_id=user_id,
                notification_type=notification_type,
                body=body,
                channel=NotificationChannel.EMAIL,
                subject=subject,
            )
        except NotificationError:
            logger.warning(
                "Failed to send monitoring notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_critical_health_change(self, user_id: str, *, target_name: str) -> None:
        """Notify *user_id* a target's own health became critical ("Critical Health Change")."""
        await self._send(
            user_id=user_id,
            body=f"Target '{target_name}' health changed to a critical status.",
            subject="An AI-IOS monitored target's health is critical",
            notification_type=NotificationType.ERROR,
        )

    async def send_availability_issue(self, user_id: str, *, target_name: str) -> None:
        """Notify *user_id* a target's own availability degraded ("Availability Issue")."""
        await self._send(
            user_id=user_id,
            body=f"Target '{target_name}' is currently unavailable or degraded.",
            subject="An AI-IOS monitored target has an availability issue",
            notification_type=NotificationType.WARNING,
        )

    async def send_synthetic_failure(self, user_id: str, *, test_name: str) -> None:
        """Notify *user_id* a synthetic check failed ("Synthetic Failure")."""
        await self._send(
            user_id=user_id,
            body=f"Synthetic test '{test_name}' failed.",
            subject="An AI-IOS synthetic monitoring test failed",
            notification_type=NotificationType.ERROR,
        )

    async def send_threshold_exceeded(self, user_id: str, *, metric_name: str) -> None:
        """Notify *user_id* a metric breached a configured threshold ("Threshold Exceeded")."""
        await self._send(
            user_id=user_id,
            body=f"Metric '{metric_name}' exceeded a configured threshold.",
            subject="An AI-IOS monitoring threshold was exceeded",
            notification_type=NotificationType.WARNING,
        )

    async def send_capacity_warning(self, user_id: str, *, target_name: str) -> None:
        """Notify *user_id* a target is approaching a capacity limit ("Capacity Warning")."""
        await self._send(
            user_id=user_id,
            body=f"Target '{target_name}' is approaching a capacity limit.",
            subject="An AI-IOS monitored target is approaching capacity",
            notification_type=NotificationType.WARNING,
        )

    async def send_monitoring_failure(self, user_id: str, *, collector_name: str) -> None:
        """Notify *user_id* a collector itself failed to run ("Monitoring Failure")."""
        await self._send(
            user_id=user_id,
            body=f"Collector '{collector_name}' failed to complete a collection run.",
            subject="An AI-IOS monitoring collector failed",
            notification_type=NotificationType.ERROR,
        )


__all__ = ["MonitoringNotificationService"]
