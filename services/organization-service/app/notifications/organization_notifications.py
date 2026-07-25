"""Organization notifications.

Per docs/033 "NOTIFICATIONS": Organization Created, Invitation,
Subscription Expiring, License Expiring, Quota Warning, Quota
Exceeded, Organization Suspended. "Integrate Prompt 025." Thin wrapper
over :class:`shared_core.notifications.manager.NotificationManager`,
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

logger = get_logger("app.notifications.organization_notifications")


class OrganizationNotificationService:
    """Sends every organization-related notification this service triggers, best-effort."""

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
                "Failed to send organization notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_organization_created(self, user_id: str, *, organization_name: str) -> None:
        """Notify *user_id* their organization was created ("Organization Created")."""
        await self._send(
            user_id=user_id,
            body=f"Your organization '{organization_name}' has been created.",
            subject="Your AI-IOS organization is ready",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_invitation(self, email: str, *, invite_url: str, message: str | None) -> None:
        """Send the "Invitation" email carrying the accept link."""
        body = f"You've been invited to join an AI-IOS organization: {invite_url}"
        if message:
            body = f"{message}\n\n{body}"
        await self._send(
            user_id=email,
            body=body,
            subject="You're invited to join an AI-IOS organization",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_invitation_reminder(self, email: str, *, invite_url: str) -> None:
        """Send the "Invitation Reminder" email."""
        await self._send(
            user_id=email,
            body=f"Reminder: your organization invitation is still open: {invite_url}",
            subject="Reminder: your AI-IOS organization invitation",
            notification_type=NotificationType.REMINDER,
        )

    async def send_subscription_expiring(self, user_id: str, *, days_remaining: int) -> None:
        """Send the "Subscription Expiring" warning."""
        await self._send(
            user_id=user_id,
            body=f"Your organization's subscription expires in {days_remaining} day(s).",
            subject="Your AI-IOS subscription is expiring soon",
            notification_type=NotificationType.WARNING,
        )

    async def send_license_expiring(self, user_id: str, *, days_remaining: int) -> None:
        """Send the "License Expiring" warning."""
        await self._send(
            user_id=user_id,
            body=f"Your organization's license expires in {days_remaining} day(s).",
            subject="Your AI-IOS license is expiring soon",
            notification_type=NotificationType.WARNING,
        )

    async def send_quota_warning(self, user_id: str, *, quota_name: str) -> None:
        """Send the "Quota Warning" notice."""
        await self._send(
            user_id=user_id,
            body=f"Your organization is approaching its '{quota_name}' quota.",
            subject="Your AI-IOS quota is almost reached",
            notification_type=NotificationType.WARNING,
        )

    async def send_quota_exceeded(self, user_id: str, *, quota_name: str) -> None:
        """Send the "Quota Exceeded" notice."""
        await self._send(
            user_id=user_id,
            body=f"Your organization has exceeded its '{quota_name}' quota.",
            subject="Your AI-IOS quota has been exceeded",
            notification_type=NotificationType.ERROR,
        )

    async def send_organization_suspended(self, user_id: str, *, reason: str) -> None:
        """Send the "Organization Suspended" notice."""
        await self._send(
            user_id=user_id,
            body=f"Your organization has been suspended: {reason}",
            subject="Your AI-IOS organization has been suspended",
            notification_type=NotificationType.CRITICAL,
        )


__all__ = ["OrganizationNotificationService"]
