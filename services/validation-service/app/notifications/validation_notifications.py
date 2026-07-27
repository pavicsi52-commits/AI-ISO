"""Validation service notifications.

Per docs/043 "NOTIFICATIONS" "Notify": Validation Started, Validation
Completed, Validation Failed, Critical Validation Failed, Compliance
Failure, Validation Timeout, Remediation Available. Thin wrapper over
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

logger = get_logger("app.notifications.validation_notifications")


class ValidationNotificationService:
    """Sends every validation-related notification this service triggers, best-effort."""

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
                "Failed to send validation notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_validation_started(self, user_id: str, *, profile_name: str) -> None:
        """Notify *user_id* a validation execution started ("Validation Started")."""
        await self._send(
            user_id=user_id,
            body=f"Validation profile '{profile_name}' has started running.",
            subject="An AI-IOS validation started",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_validation_completed(self, user_id: str, *, profile_name: str) -> None:
        """Notify *user_id* a validation execution completed ("Validation Completed")."""
        await self._send(
            user_id=user_id,
            body=f"Validation profile '{profile_name}' completed successfully.",
            subject="An AI-IOS validation completed",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_validation_failed(self, user_id: str, *, profile_name: str) -> None:
        """Notify *user_id* a validation execution failed ("Validation Failed")."""
        await self._send(
            user_id=user_id,
            body=f"Validation profile '{profile_name}' failed.",
            subject="An AI-IOS validation failed",
            notification_type=NotificationType.ERROR,
        )

    async def send_critical_validation_failed(self, user_id: str, *, profile_name: str) -> None:
        """Notify *user_id* a critical-severity failure was found
        ("Critical Validation Failed").
        """
        await self._send(
            user_id=user_id,
            body=f"Validation profile '{profile_name}' found a critical failure.",
            subject="An AI-IOS validation found a critical failure",
            notification_type=NotificationType.ERROR,
        )

    async def send_compliance_failure(self, user_id: str, *, profile_name: str) -> None:
        """Notify *user_id* a compliance check failed ("Compliance Failure")."""
        await self._send(
            user_id=user_id,
            body=f"Validation profile '{profile_name}' found a compliance failure.",
            subject="An AI-IOS validation found a compliance failure",
            notification_type=NotificationType.WARNING,
        )

    async def send_validation_timeout(self, user_id: str, *, profile_name: str) -> None:
        """Notify *user_id* a validation execution timed out ("Validation Timeout")."""
        await self._send(
            user_id=user_id,
            body=f"Validation profile '{profile_name}' timed out.",
            subject="An AI-IOS validation timed out",
            notification_type=NotificationType.ERROR,
        )

    async def send_remediation_available(self, user_id: str, *, profile_name: str) -> None:
        """Notify *user_id* a remediation suggestion is available ("Remediation Available")."""
        await self._send(
            user_id=user_id,
            body=f"A remediation suggestion is available for validation profile '{profile_name}'.",
            subject="An AI-IOS remediation suggestion is available",
            notification_type=NotificationType.INFORMATION,
        )


__all__ = ["ValidationNotificationService"]
