"""Scheduler notifications (docs/054 "NOTIFICATIONS").

Integrates ``shared_core``'s notification manager (Prompt 025) using the
best-effort ``_send`` pattern every prior AI-IOS service established:
**a notification failure never blocks the operation that triggered it.**
A job execution still gets recorded as failed even if the alert that was
supposed to announce it never went out -- the alternative would mean an
unreachable mail server silently disables the platform's own failure
visibility at exactly the moment it is needed.
"""

from __future__ import annotations

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.exceptions.notification import NotificationError
from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager

logger = get_logger("app.notifications.scheduler_notifications")


class SchedulerNotificationService:
    """Sends every scheduler notification, best-effort."""

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
                "Failed to send a scheduler notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_job_failed(self, user_id: str, *, job_name: str, error: str) -> None:
        """Notify a job's owner that an execution failed."""
        await self._send(
            user_id=user_id,
            subject=f"Job failed: {job_name}",
            body=f"{job_name} failed: {error}",
            notification_type=NotificationType.ERROR,
        )

    async def send_job_completed(self, user_id: str, *, job_name: str) -> None:
        """Notify a job's owner that an execution completed."""
        await self._send(
            user_id=user_id,
            subject=f"Job completed: {job_name}",
            body=f"{job_name} completed successfully.",
            notification_type=NotificationType.SUCCESS,
        )

    async def send_retry_started(
        self, user_id: str, *, job_name: str, attempt_number: int, max_attempts: int
    ) -> None:
        """Notify a job's owner that a retry attempt has begun."""
        await self._send(
            user_id=user_id,
            subject=f"Retrying: {job_name}",
            body=f"{job_name} is retrying (attempt {attempt_number} of {max_attempts}).",
            notification_type=NotificationType.WARNING,
        )

    async def send_maintenance_started(self, user_id: str, *, window_title: str) -> None:
        """Notify a subscriber that a maintenance window has opened."""
        await self._send(
            user_id=user_id,
            subject=f"Maintenance started: {window_title}",
            body=f"The maintenance window {window_title!r} is now active.",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_maintenance_ended(self, user_id: str, *, window_title: str) -> None:
        """Notify a subscriber that a maintenance window has ended."""
        await self._send(
            user_id=user_id,
            subject=f"Maintenance ended: {window_title}",
            body=f"The maintenance window {window_title!r} has ended.",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_scheduler_failure(self, user_id: str, *, detail: str) -> None:
        """Notify an operator that the scheduler itself hit an operational failure.

        Distinct from ``send_job_failed`` -- this is the platform's own
        sweep or dispatch machinery failing, not a job's own work."""
        await self._send(
            user_id=user_id,
            subject="Scheduler failure",
            body=detail,
            notification_type=NotificationType.ERROR,
        )

    async def send_recovery_completed(self, user_id: str, *, job_name: str, action: str) -> None:
        """Notify a job's owner that a failure was recovered."""
        await self._send(
            user_id=user_id,
            subject=f"Recovered: {job_name}",
            body=f"{job_name} was recovered via {action}.",
            notification_type=NotificationType.SUCCESS,
        )


__all__ = ["SchedulerNotificationService"]
