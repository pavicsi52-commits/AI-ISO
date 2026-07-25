"""User management notifications.

Per docs/031 "NOTIFICATIONS": Invitation, Invitation Reminder, Profile
Updated, Account Activated, Account Suspended, Account Deleted.
"Integrate Prompt 025." Thin wrapper over
:class:`shared_core.notifications.manager.NotificationManager`. There
is no ``ACCOUNT``-flavored :class:`~shared_core.enums.notification_type
.NotificationType` member (that enum is about *urgency/kind*, not
*domain*) -- every send here uses ``INFORMATION`` over
:data:`~shared_core.enums.notification_channel.NotificationChannel
.EMAIL`, the closest fit for "here's what happened to your account."

Every send is best-effort: a notification failure (no channel
configured, SMTP unreachable, ...) is logged and swallowed rather than
propagated, matching ``services/authentication-service``'s
``AuthNotificationService`` precedent -- and the exact real bug that
precedent was created to fix (a missing-SMTP-channel failure blocking
the triggering operation entirely).
"""

from __future__ import annotations

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.exceptions.notification import NotificationError
from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager

logger = get_logger("app.notifications.user_notifications")


class UserNotificationService:
    """Sends every user-management-related email this service triggers, best-effort."""

    def __init__(self, manager: NotificationManager) -> None:
        self._manager = manager

    async def _send(self, *, user_id: str, body: str, subject: str) -> None:
        try:
            await self._manager.send(
                user_id=user_id,
                notification_type=NotificationType.INFORMATION,
                body=body,
                channel=NotificationChannel.EMAIL,
                subject=subject,
            )
        except NotificationError:
            logger.warning(
                "Failed to send user-management notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_invitation(self, email: str, *, invite_url: str, message: str | None) -> None:
        """Send the "Invitation" email carrying the accept link."""
        body = f"You've been invited to join AI-IOS: {invite_url}"
        if message:
            body = f"{message}\n\n{body}"
        await self._send(user_id=email, body=body, subject="You're invited to AI-IOS")

    async def send_invitation_reminder(self, email: str, *, invite_url: str) -> None:
        """Send the "Invitation Reminder" email."""
        await self._send(
            user_id=email,
            body=f"Reminder: your AI-IOS invitation is still open: {invite_url}",
            subject="Reminder: your AI-IOS invitation",
        )

    async def send_profile_updated(self, user_id: str) -> None:
        """Send the "Profile Updated" confirmation."""
        await self._send(
            user_id=user_id,
            body="Your profile was just updated. If this wasn't you, contact support.",
            subject="Your AI-IOS profile was updated",
        )

    async def send_account_activated(self, user_id: str) -> None:
        """Send the "Account Activated" notice."""
        await self._send(
            user_id=user_id,
            body="Your AI-IOS account is now active.",
            subject="Your AI-IOS account is active",
        )

    async def send_account_suspended(self, user_id: str) -> None:
        """Send the "Account Suspended" notice."""
        await self._send(
            user_id=user_id,
            body="Your AI-IOS account has been suspended. Contact your administrator.",
            subject="Your AI-IOS account has been suspended",
        )

    async def send_account_deleted(self, user_id: str) -> None:
        """Send the "Account Deleted" notice."""
        await self._send(
            user_id=user_id,
            body="Your AI-IOS account has been deleted.",
            subject="Your AI-IOS account has been deleted",
        )


__all__ = ["UserNotificationService"]
