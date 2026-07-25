"""Automation service notifications.

Per docs/040 "NOTIFICATIONS" "Notify": Execution Started, Execution
Completed, Execution Failed, Approval Required, Rollback Completed,
Critical Failure, Long Running Job, Schedule Missed. Thin wrapper over
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

logger = get_logger("app.notifications.automation_notifications")


class AutomationNotificationService:
    """Sends every automation-related notification this service triggers, best-effort."""

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
                "Failed to send automation notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_execution_started(self, user_id: str, *, job_name: str) -> None:
        """Notify *user_id* an execution started ("Execution Started")."""
        await self._send(
            user_id=user_id,
            body=f"Automation job '{job_name}' has started executing.",
            subject="An AI-IOS automation execution started",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_execution_completed(self, user_id: str, *, job_name: str) -> None:
        """Notify *user_id* an execution completed ("Execution Completed")."""
        await self._send(
            user_id=user_id,
            body=f"Automation job '{job_name}' completed successfully.",
            subject="An AI-IOS automation execution completed",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_execution_failed(self, user_id: str, *, job_name: str) -> None:
        """Notify *user_id* an execution failed ("Execution Failed")."""
        await self._send(
            user_id=user_id,
            body=f"Automation job '{job_name}' failed to complete.",
            subject="An AI-IOS automation execution failed",
            notification_type=NotificationType.ERROR,
        )

    async def send_approval_required(self, user_id: str, *, job_name: str) -> None:
        """Notify *user_id* an approval gate is blocking a job ("Approval Required")."""
        await self._send(
            user_id=user_id,
            body=f"Automation job '{job_name}' is waiting on your approval.",
            subject="An AI-IOS automation approval is required",
            notification_type=NotificationType.WARNING,
        )

    async def send_rollback_completed(self, user_id: str, *, job_name: str) -> None:
        """Notify *user_id* a rollback completed ("Rollback Completed")."""
        await self._send(
            user_id=user_id,
            body=f"A rollback for automation job '{job_name}' has completed.",
            subject="An AI-IOS automation rollback completed",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_critical_failure(self, user_id: str, *, job_name: str, reason: str) -> None:
        """Notify *user_id* of a critical failure ("Critical Failure")."""
        await self._send(
            user_id=user_id,
            body=f"Automation job '{job_name}' hit a critical failure: {reason}",
            subject="An AI-IOS automation critical failure occurred",
            notification_type=NotificationType.ERROR,
        )

    async def send_long_running_job(self, user_id: str, *, job_name: str, seconds: float) -> None:
        """Notify *user_id* a job has run longer than expected ("Long Running Job")."""
        await self._send(
            user_id=user_id,
            body=f"Automation job '{job_name}' has been running for {seconds:.0f} seconds.",
            subject="An AI-IOS automation job is running long",
            notification_type=NotificationType.WARNING,
        )

    async def send_schedule_missed(self, user_id: str, *, job_name: str) -> None:
        """Notify *user_id* a scheduled run was missed ("Schedule Missed")."""
        await self._send(
            user_id=user_id,
            body=f"A scheduled run for automation job '{job_name}' was missed.",
            subject="An AI-IOS automation schedule was missed",
            notification_type=NotificationType.WARNING,
        )


__all__ = ["AutomationNotificationService"]
