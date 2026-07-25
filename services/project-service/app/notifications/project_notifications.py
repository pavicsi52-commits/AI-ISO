"""Project notifications.

Per docs/034 "NOTIFICATIONS": Project Created, Invitation Sent,
Invitation Accepted, Ownership Changed, Project Archived, Project
Restored, Project Deleted. "Integrate Prompt 025." Thin wrapper over
:class:`shared_core.notifications.manager.NotificationManager`, the
same best-effort ``_send()`` pattern every prior AI-IOS service's own
notification service established -- a notification failure never
blocks the triggering operation.

**Scope note**: docs/034's own "PROJECT MEMBERS" section supports
direct member addition, not an email-based invitation flow the way
``services/organization-service``'s own membership does -- there is no
"Invite Member" REST endpoint in docs/034's endpoint list, only
``POST /projects/{id}/members``. "Invitation Sent"/"Invitation
Accepted" are still implemented here (as notifications fired around
direct membership addition) since docs/034 explicitly names them, but
there is no separate token-based accept/reject flow to back, unlike
organization-service's own invitations.
"""

from __future__ import annotations

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.exceptions.notification import NotificationError
from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager

logger = get_logger("app.notifications.project_notifications")


class ProjectNotificationService:
    """Sends every project-related notification this service triggers, best-effort."""

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
                "Failed to send project notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_project_created(self, user_id: str, *, project_name: str) -> None:
        """Notify *user_id* their project was created ("Project Created")."""
        await self._send(
            user_id=user_id,
            body=f"Your project '{project_name}' has been created.",
            subject="Your AI-IOS project is ready",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_invitation_sent(self, user_id: str, *, project_name: str) -> None:
        """Notify *user_id* they were added to a project ("Invitation Sent")."""
        await self._send(
            user_id=user_id,
            body=f"You've been added to the project '{project_name}'.",
            subject="You've been added to an AI-IOS project",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_invitation_accepted(self, user_id: str, *, member_name: str) -> None:
        """Notify a project admin a member joined ("Invitation Accepted")."""
        await self._send(
            user_id=user_id,
            body=f"{member_name} has joined your project.",
            subject="A new member joined your AI-IOS project",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_ownership_changed(self, user_id: str, *, project_name: str) -> None:
        """Notify the new owner of a project ownership transfer ("Ownership Changed")."""
        await self._send(
            user_id=user_id,
            body=f"You are now the owner of the project '{project_name}'.",
            subject="You are now the owner of an AI-IOS project",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_project_archived(self, user_id: str, *, project_name: str) -> None:
        """Notify *user_id* their project was archived ("Project Archived")."""
        await self._send(
            user_id=user_id,
            body=f"Your project '{project_name}' has been archived.",
            subject="Your AI-IOS project has been archived",
            notification_type=NotificationType.WARNING,
        )

    async def send_project_restored(self, user_id: str, *, project_name: str) -> None:
        """Notify *user_id* their project was restored ("Project Restored")."""
        await self._send(
            user_id=user_id,
            body=f"Your project '{project_name}' has been restored.",
            subject="Your AI-IOS project has been restored",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_project_deleted(self, user_id: str, *, project_name: str) -> None:
        """Notify *user_id* their project was deleted ("Project Deleted")."""
        await self._send(
            user_id=user_id,
            body=f"Your project '{project_name}' has been deleted.",
            subject="Your AI-IOS project has been deleted",
            notification_type=NotificationType.CRITICAL,
        )


__all__ = ["ProjectNotificationService"]
