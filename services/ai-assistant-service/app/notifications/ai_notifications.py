"""AI assistant notifications.

Per docs/046 "NOTIFICATIONS" "Notify": Long Running AI Tasks, Report
Completion, Recommendation Ready, Model Failure, Tool Failure. A thin
wrapper over :class:`shared_core.notifications.manager
.NotificationManager` using the same best-effort ``_send`` pattern every
prior AI-IOS service established -- a notification failure never blocks
the operation that triggered it.
"""

from __future__ import annotations

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.exceptions.notification import NotificationError
from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager

logger = get_logger("app.notifications.ai_notifications")


class AiNotificationService:
    """Sends every AI-related notification, best-effort."""

    def __init__(self, manager: NotificationManager) -> None:
        self._manager = manager

    async def _send(
        self, *, user_id: str, subject: str, body: str, notification_type: NotificationType
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
                "Failed to send AI notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_long_running_task(self, user_id: str, *, description: str) -> None:
        """Notify that a long-running AI task is still working."""
        await self._send(
            user_id=user_id,
            subject="An AI-IOS assistant task is still running",
            body=f"The assistant is still working on: {description}.",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_report_ready(self, user_id: str, *, title: str) -> None:
        """Notify that a generated report is ready."""
        await self._send(
            user_id=user_id,
            subject="An AI-IOS report is ready",
            body=f"The report '{title}' has finished generating.",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_recommendation_ready(self, user_id: str, *, title: str) -> None:
        """Notify that a recommendation awaits review."""
        await self._send(
            user_id=user_id,
            subject="An AI-IOS recommendation is ready for review",
            body=f"The assistant generated a recommendation: '{title}'.",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_model_failure(self, user_id: str, *, provider: str, reason: str) -> None:
        """Notify that every model provider failed."""
        await self._send(
            user_id=user_id,
            subject="An AI-IOS model provider failed",
            body=f"Model provider '{provider}' could not be reached: {reason}",
            notification_type=NotificationType.ERROR,
        )

    async def send_tool_failure(self, user_id: str, *, tool_key: str, reason: str) -> None:
        """Notify that a tool invocation failed."""
        await self._send(
            user_id=user_id,
            subject="An AI-IOS assistant tool failed",
            body=f"Tool '{tool_key}' failed: {reason}",
            notification_type=NotificationType.ERROR,
        )


__all__ = ["AiNotificationService"]
