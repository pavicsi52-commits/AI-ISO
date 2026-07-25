"""Secrets management notifications.

Per docs/035 "NOTIFICATIONS": Secret Expiring, Certificate Expiring,
Rotation Failed, Rotation Completed, Lease Expired, Unauthorized Access
Attempt. "Integrate Prompt 025." Thin wrapper over
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

logger = get_logger("app.notifications.secret_notifications")


class SecretNotificationService:
    """Sends every secrets-management notification this service triggers, best-effort."""

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
                "Failed to send secrets-management notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_secret_expiring(self, user_id: str, *, secret_name: str, days_left: int) -> None:
        """Notify *user_id* a secret is approaching expiration ("Secret Expiring")."""
        await self._send(
            user_id=user_id,
            body=f"The secret '{secret_name}' expires in {days_left} day(s).",
            subject="An AI-IOS secret is expiring soon",
            notification_type=NotificationType.WARNING,
        )

    async def send_certificate_expiring(
        self, user_id: str, *, certificate_name: str, days_left: int
    ) -> None:
        """Notify *user_id* a certificate is approaching expiration ("Certificate Expiring")."""
        await self._send(
            user_id=user_id,
            body=f"The certificate '{certificate_name}' expires in {days_left} day(s).",
            subject="An AI-IOS certificate is expiring soon",
            notification_type=NotificationType.WARNING,
        )

    async def send_rotation_failed(
        self, user_id: str, *, secret_name: str, error_message: str
    ) -> None:
        """Notify *user_id* a rotation attempt failed ("Rotation Failed")."""
        await self._send(
            user_id=user_id,
            body=f"Rotation of the secret '{secret_name}' failed: {error_message}",
            subject="An AI-IOS secret rotation failed",
            notification_type=NotificationType.CRITICAL,
        )

    async def send_rotation_completed(self, user_id: str, *, secret_name: str) -> None:
        """Notify *user_id* a rotation completed successfully ("Rotation Completed")."""
        await self._send(
            user_id=user_id,
            body=f"The secret '{secret_name}' was rotated successfully.",
            subject="An AI-IOS secret was rotated",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_lease_expired(self, user_id: str, *, secret_name: str) -> None:
        """Notify *user_id* one of their leases expired ("Lease Expired")."""
        await self._send(
            user_id=user_id,
            body=f"Your lease on the secret '{secret_name}' has expired.",
            subject="An AI-IOS secret lease expired",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_unauthorized_access_attempt(
        self, user_id: str, *, secret_name: str, actor_id: str
    ) -> None:
        """Notify *user_id* (the secret's owner) of a denied access attempt
        ("Unauthorized Access Attempt")."""
        await self._send(
            user_id=user_id,
            body=f"An unauthorized access attempt on the secret '{secret_name}' "
            f"was blocked (actor: {actor_id}).",
            subject="Unauthorized AI-IOS secret access attempt blocked",
            notification_type=NotificationType.CRITICAL,
        )


__all__ = ["SecretNotificationService"]
