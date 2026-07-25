"""RBAC notifications.

Per docs/032 "NOTIFICATIONS": Role Assignment, Permission Changes,
Policy Changes, Security Violations, Unauthorized Access Attempts.
"Integrate Prompt 025." Thin wrapper over
:class:`shared_core.notifications.manager.NotificationManager`, same
best-effort ``_send()`` pattern as
``services/user-management-service``'s ``UserNotificationService`` --
a notification failure never blocks the triggering authorization
operation. Routine changes use
:attr:`~shared_core.enums.notification_type.NotificationType
.INFORMATION`; "Security Violations"/"Unauthorized Access Attempts" use
:attr:`~shared_core.enums.notification_type.NotificationType.SECURITY`,
the closest fit shared-core actually defines for that urgency.
"""

from __future__ import annotations

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.exceptions.notification import NotificationError
from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager

logger = get_logger("app.notifications.rbac_notifications")


class RbacNotificationService:
    """Sends every RBAC-related notification this service triggers, best-effort."""

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
                "Failed to send RBAC notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_role_assigned(self, user_id: str, *, role_name: str) -> None:
        """Notify *user_id* they were granted a role ("Role Assignment")."""
        await self._send(
            user_id=user_id,
            body=f"You have been assigned the role '{role_name}'.",
            subject="A role was assigned to your AI-IOS account",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_role_removed(self, user_id: str, *, role_name: str) -> None:
        """Notify *user_id* a role was removed from them ("Role Assignment")."""
        await self._send(
            user_id=user_id,
            body=f"The role '{role_name}' was removed from your account.",
            subject="A role was removed from your AI-IOS account",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_permission_changed(self, user_id: str, *, permission_code: str) -> None:
        """Notify *user_id* a permission on a role they hold changed ("Permission Changes")."""
        await self._send(
            user_id=user_id,
            body=f"Permission '{permission_code}' on one of your roles has changed.",
            subject="Your AI-IOS permissions have changed",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_policy_changed(self, user_id: str, *, policy_name: str) -> None:
        """Notify *user_id* a policy affecting them changed ("Policy Changes")."""
        await self._send(
            user_id=user_id,
            body=f"The authorization policy '{policy_name}' affecting your access has changed.",
            subject="An AI-IOS access policy has changed",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_unauthorized_access_attempt(
        self, user_id: str, *, action: str, resource_type: str
    ) -> None:
        """Notify *user_id* of a denied attempt on their behalf ("Unauthorized Access Attempts")."""
        await self._send(
            user_id=user_id,
            body=f"A denied attempt to {action} {resource_type} was recorded on your account.",
            subject="Unauthorized access attempt on your AI-IOS account",
            notification_type=NotificationType.SECURITY,
        )

    async def send_security_violation(self, user_id: str, *, reason: str) -> None:
        """Notify *user_id* of a detected security violation ("Security Violations")."""
        await self._send(
            user_id=user_id,
            body=f"A security violation was detected on your account: {reason}",
            subject="Security violation detected on your AI-IOS account",
            notification_type=NotificationType.SECURITY,
        )


__all__ = ["RbacNotificationService"]
