"""Configuration management notifications.

Per docs/039 "NOTIFICATIONS": Approval Requested, Approval Completed,
Drift Detected, Compliance Failure, Backup Completed, Restore
Completed, Rollback Completed. "Integrate Prompt 025." Thin wrapper
over :class:`shared_core.notifications.manager.NotificationManager`,
the same best-effort ``_send()`` pattern every prior AI-IOS service's
own notification service established -- a notification failure never
blocks the triggering operation.
"""

from __future__ import annotations

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.exceptions.notification import NotificationError
from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager

logger = get_logger("app.notifications.configuration_notifications")


class ConfigurationNotificationService:
    """Sends every configuration-management-related notification this service triggers,
    best-effort.
    """

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
                "Failed to send configuration management notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_approval_requested(self, user_id: str, *, profile_name: str) -> None:
        """Notify *user_id* an approval is requested ("Approval Requested")."""
        await self._send(
            user_id=user_id,
            body=f"An approval is requested for configuration profile '{profile_name}'.",
            subject="An AI-IOS configuration approval is requested",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_approval_completed(
        self, user_id: str, *, profile_name: str, approved: bool
    ) -> None:
        """Notify *user_id* an approval was decided ("Approval Completed")."""
        outcome = "approved" if approved else "rejected"
        await self._send(
            user_id=user_id,
            body=f"The approval for configuration profile '{profile_name}' was {outcome}.",
            subject="An AI-IOS configuration approval completed",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_drift_detected(self, user_id: str, *, profile_name: str) -> None:
        """Notify *user_id* drift was detected ("Drift Detected")."""
        await self._send(
            user_id=user_id,
            body=f"Configuration drift was detected for profile '{profile_name}'.",
            subject="AI-IOS configuration drift detected",
            notification_type=NotificationType.WARNING,
        )

    async def send_compliance_failure(self, user_id: str, *, profile_name: str) -> None:
        """Notify *user_id* a compliance evaluation failed ("Compliance Failure")."""
        await self._send(
            user_id=user_id,
            body=f"A compliance evaluation failed for configuration profile '{profile_name}'.",
            subject="An AI-IOS configuration failed compliance",
            notification_type=NotificationType.ERROR,
        )

    async def send_backup_completed(self, user_id: str, *, profile_name: str) -> None:
        """Notify *user_id* a backup completed ("Backup Completed")."""
        await self._send(
            user_id=user_id,
            body=f"A backup of configuration profile '{profile_name}' has completed.",
            subject="An AI-IOS configuration backup completed",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_restore_completed(self, user_id: str, *, profile_name: str) -> None:
        """Notify *user_id* a restore completed ("Restore Completed")."""
        await self._send(
            user_id=user_id,
            body=f"A restore of configuration profile '{profile_name}' has completed.",
            subject="An AI-IOS configuration restore completed",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_rollback_completed(self, user_id: str, *, profile_name: str) -> None:
        """Notify *user_id* a rollback completed ("Rollback Completed")."""
        await self._send(
            user_id=user_id,
            body=f"A rollback of configuration profile '{profile_name}' has completed.",
            subject="An AI-IOS configuration rollback completed",
            notification_type=NotificationType.INFORMATION,
        )


__all__ = ["ConfigurationNotificationService"]
