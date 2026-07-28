"""Reporting notifications.

Per docs/047 "NOTIFICATIONS" "Notify": Report Ready, Report Failed,
Scheduled Report Complete, Distribution Failure, Archive Completed.

A thin wrapper over ``shared_core``'s notification manager using the
best-effort ``_send`` pattern every prior AI-IOS service established:
**a notification failure never blocks the operation that triggered
it.** A report that generated correctly must not be marked failed
because an SMTP server was down.
"""

from __future__ import annotations

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.exceptions.notification import NotificationError
from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager

logger = get_logger("app.notifications.report_notifications")


class ReportNotificationService:
    """Sends every reporting notification, best-effort."""

    def __init__(self, manager: NotificationManager) -> None:
        self._manager = manager

    async def _send(
        self, *, user_id: str, subject: str, body: str, notification_type: NotificationType
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
                "Failed to send reporting notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_report_ready(self, user_id: str, *, title: str) -> None:
        """Notify that a report finished generating."""
        await self._send(
            user_id=user_id,
            subject=f"Report ready: {title}",
            body=f"The report '{title}' has finished generating and is ready to download.",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_report_failed(self, user_id: str, *, title: str, reason: str) -> None:
        """Notify that a report failed to generate."""
        await self._send(
            user_id=user_id,
            subject=f"Report failed: {title}",
            body=f"The report '{title}' could not be generated: {reason}",
            notification_type=NotificationType.ERROR,
        )

    async def send_scheduled_complete(self, user_id: str, *, title: str) -> None:
        """Notify that an unattended scheduled run completed."""
        await self._send(
            user_id=user_id,
            subject=f"Scheduled report complete: {title}",
            body=f"The scheduled report '{title}' completed successfully.",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_distribution_failed(
        self, user_id: str, *, title: str, channel: str, reason: str
    ) -> None:
        """Notify that a delivery attempt failed."""
        await self._send(
            user_id=user_id,
            subject=f"Report delivery failed: {title}",
            body=f"Delivering '{title}' over {channel} failed: {reason}",
            notification_type=NotificationType.ERROR,
        )

    async def send_archive_completed(self, user_id: str, *, title: str) -> None:
        """Notify that an artifact was archived."""
        await self._send(
            user_id=user_id,
            subject=f"Report archived: {title}",
            body=f"The report '{title}' has been archived and is retained per policy.",
            notification_type=NotificationType.INFORMATION,
        )


__all__ = ["ReportNotificationService"]
