"""Workflow runtime service notifications.

Per docs/042 "NOTIFICATIONS" "Notify": Workflow Started, Workflow
Completed, Workflow Failed, Approval Required, Timeout, Rollback
Completed, Replay Completed. Thin wrapper over
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

logger = get_logger("app.notifications.workflow_notifications")


class WorkflowNotificationService:
    """Sends every workflow-related notification this service triggers, best-effort."""

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
                "Failed to send workflow notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_workflow_started(self, user_id: str, *, workflow_name: str) -> None:
        """Notify *user_id* a workflow instance started ("Workflow Started")."""
        await self._send(
            user_id=user_id,
            body=f"Workflow '{workflow_name}' has started running.",
            subject="An AI-IOS workflow started",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_workflow_completed(self, user_id: str, *, workflow_name: str) -> None:
        """Notify *user_id* a workflow instance completed ("Workflow Completed")."""
        await self._send(
            user_id=user_id,
            body=f"Workflow '{workflow_name}' completed successfully.",
            subject="An AI-IOS workflow completed",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_workflow_failed(self, user_id: str, *, workflow_name: str) -> None:
        """Notify *user_id* a workflow instance failed ("Workflow Failed")."""
        await self._send(
            user_id=user_id,
            body=f"Workflow '{workflow_name}' failed.",
            subject="An AI-IOS workflow failed",
            notification_type=NotificationType.ERROR,
        )

    async def send_approval_required(self, user_id: str, *, workflow_name: str) -> None:
        """Notify *user_id* an approval is required ("Approval Required")."""
        await self._send(
            user_id=user_id,
            body=f"An approval is required for workflow '{workflow_name}'.",
            subject="An AI-IOS workflow approval is required",
            notification_type=NotificationType.WARNING,
        )

    async def send_timeout(self, user_id: str, *, workflow_name: str) -> None:
        """Notify *user_id* a workflow instance timed out ("Timeout")."""
        await self._send(
            user_id=user_id,
            body=f"Workflow '{workflow_name}' timed out.",
            subject="An AI-IOS workflow timed out",
            notification_type=NotificationType.ERROR,
        )

    async def send_rollback_completed(self, user_id: str, *, workflow_name: str) -> None:
        """Notify *user_id* a rollback completed ("Rollback Completed")."""
        await self._send(
            user_id=user_id,
            body=f"Workflow '{workflow_name}' was rolled back.",
            subject="An AI-IOS workflow rollback completed",
            notification_type=NotificationType.WARNING,
        )

    async def send_replay_completed(self, user_id: str, *, workflow_name: str) -> None:
        """Notify *user_id* a replay completed ("Replay Completed")."""
        await self._send(
            user_id=user_id,
            body=f"Workflow '{workflow_name}' replay completed.",
            subject="An AI-IOS workflow replay completed",
            notification_type=NotificationType.INFORMATION,
        )


__all__ = ["WorkflowNotificationService"]
