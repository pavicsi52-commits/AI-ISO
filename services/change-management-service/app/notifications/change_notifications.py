"""Change notifications (docs/053 "NOTIFICATIONS").

Integrates ``shared_core``'s notification manager (Prompt 025) using the
best-effort ``_send`` pattern every prior AI-IOS service established:
**a notification failure never blocks the operation that triggered it.**
A CAB meeting still gets recorded as scheduled even if the invite that
was supposed to announce it never went out -- the alternative would mean
an unreachable mail server silently disables the platform's own change
process at exactly the moment it is needed.
"""

from __future__ import annotations

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.exceptions.notification import NotificationError
from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager

logger = get_logger("app.notifications.change_notifications")


class ChangeNotificationService:
    """Sends every change-management notification, best-effort."""

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
                "Failed to send a change notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_approval_required(
        self, user_id: str, *, reference: str, title: str, level: int
    ) -> None:
        """Notify an approver that a change is waiting on their decision."""
        await self._send(
            user_id=user_id,
            subject=f"Approval required (level {level}): {reference}",
            body=f"{reference} -- {title} -- is waiting on your approval at level {level}.",
            notification_type=NotificationType.WARNING,
        )

    async def send_cab_meeting_scheduled(
        self, user_id: str, *, reference: str, title: str, scheduled_at: str
    ) -> None:
        """Notify a board member that a CAB review has been scheduled."""
        await self._send(
            user_id=user_id,
            subject=f"CAB review scheduled: {reference}",
            body=f"{reference} -- {title} -- goes before the board at {scheduled_at}.",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_implementation_started(
        self, user_id: str, *, reference: str, title: str
    ) -> None:
        """Notify a change's owner that implementation has begun."""
        await self._send(
            user_id=user_id,
            subject=f"Implementation started: {reference}",
            body=f"{reference} -- {title} -- has entered implementation.",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_implementation_completed(
        self, user_id: str, *, reference: str, title: str, status: str
    ) -> None:
        """Notify a change's owner that implementation has finished."""
        await self._send(
            user_id=user_id,
            subject=f"Implementation {status}: {reference}",
            body=f"{reference} -- {title} -- implementation finished as {status}.",
            notification_type=(
                NotificationType.SUCCESS if status == "completed" else NotificationType.ERROR
            ),
        )

    async def send_validation_failed(
        self, user_id: str, *, reference: str, title: str, validation_kind: str
    ) -> None:
        """Notify a change's owner that a validation gate failed.

        Sent distinctly from ``send_implementation_completed``, because
        the failure of a single gate and the overall outcome of the run
        are two separate facts -- a recipient who only gets the second
        cannot tell from it alone which check was the one that failed.
        """
        await self._send(
            user_id=user_id,
            subject=f"Validation failed ({validation_kind}): {reference}",
            body=f"{reference} -- {title} -- failed its {validation_kind} validation.",
            notification_type=NotificationType.ERROR,
        )

    async def send_rollback_started(
        self, user_id: str, *, reference: str, title: str, reason: str
    ) -> None:
        """Notify a change's owner that a rollback has begun."""
        await self._send(
            user_id=user_id,
            subject=f"Rollback started: {reference}",
            body=f"{reference} -- {title} -- is being rolled back. Reason: {reason}",
            notification_type=NotificationType.ERROR,
        )

    async def send_pir_due(
        self, user_id: str, *, reference: str, title: str, completed_days_ago: int
    ) -> None:
        """Remind an owner that a post-implementation review is overdue.

        The reminder a PIR process actually depends on: a review that
        never gets written is the single most common way a lessons-
        learned process quietly stops producing any lessons.
        """
        await self._send(
            user_id=user_id,
            subject=f"PIR overdue: {reference}",
            body=(
                f"{reference} -- {title} -- completed implementation "
                f"{completed_days_ago} day(s) ago and has no post-implementation review yet."
            ),
            notification_type=NotificationType.WARNING,
        )


__all__ = ["ChangeNotificationService"]
