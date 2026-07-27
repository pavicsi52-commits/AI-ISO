"""Playbook service notifications.

Per docs/041 "NOTIFICATIONS" "Notify": Approval Requested, Approval
Completed, Validation Failed, Content Published, Content Deprecated,
Signature Failed. Thin wrapper over :class:`shared_core.notifications
.manager.NotificationManager`, the same best-effort ``_send()`` pattern
every prior AI-IOS service's own notification service established --
a notification failure never blocks the triggering operation.
"""

from __future__ import annotations

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.exceptions.notification import NotificationError
from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager

logger = get_logger("app.notifications.playbook_notifications")


class PlaybookNotificationService:
    """Sends every playbook-related notification this service triggers, best-effort."""

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
                "Failed to send playbook notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_approval_requested(self, user_id: str, *, playbook_name: str) -> None:
        """Notify *user_id* an approval is requested ("Approval Requested")."""
        await self._send(
            user_id=user_id,
            body=f"An approval is requested for playbook '{playbook_name}'.",
            subject="An AI-IOS playbook approval is requested",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_approval_completed(
        self, user_id: str, *, playbook_name: str, approved: bool
    ) -> None:
        """Notify *user_id* an approval was decided ("Approval Completed")."""
        outcome = "approved" if approved else "rejected"
        await self._send(
            user_id=user_id,
            body=f"The approval for playbook '{playbook_name}' was {outcome}.",
            subject="An AI-IOS playbook approval completed",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_validation_failed(self, user_id: str, *, playbook_name: str) -> None:
        """Notify *user_id* content validation failed ("Validation Failed")."""
        await self._send(
            user_id=user_id,
            body=f"Content validation failed for playbook '{playbook_name}'.",
            subject="An AI-IOS playbook failed validation",
            notification_type=NotificationType.ERROR,
        )

    async def send_content_published(self, user_id: str, *, playbook_name: str) -> None:
        """Notify *user_id* a playbook was published ("Content Published")."""
        await self._send(
            user_id=user_id,
            body=f"Playbook '{playbook_name}' has been published.",
            subject="An AI-IOS playbook was published",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_content_deprecated(self, user_id: str, *, playbook_name: str) -> None:
        """Notify *user_id* a playbook was deprecated ("Content Deprecated")."""
        await self._send(
            user_id=user_id,
            body=f"Playbook '{playbook_name}' has been deprecated.",
            subject="An AI-IOS playbook was deprecated",
            notification_type=NotificationType.WARNING,
        )

    async def send_signature_failed(self, user_id: str, *, playbook_name: str) -> None:
        """Notify *user_id* signature verification failed ("Signature Failed")."""
        await self._send(
            user_id=user_id,
            body=f"Digital signature verification failed for playbook '{playbook_name}'.",
            subject="An AI-IOS playbook signature verification failed",
            notification_type=NotificationType.ERROR,
        )


__all__ = ["PlaybookNotificationService"]
