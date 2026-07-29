"""Dashboard notifications.

Per docs/048 "NOTIFICATIONS" "Notify": Dashboard Shared, Layout
Updated, Widget Failure, Real-time Connection Lost, Refresh Failure.

A thin wrapper over ``shared_core``'s notification manager using the
best-effort ``_send`` pattern every prior AI-IOS service established:
**a notification failure never blocks the operation that triggered
it.** A dashboard that loaded correctly must not report an error
because an SMTP server was down.
"""

from __future__ import annotations

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.exceptions.notification import NotificationError
from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager

logger = get_logger("app.notifications.dashboard_notifications")


class DashboardNotificationService:
    """Sends every dashboard notification, best-effort."""

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
                "Failed to send dashboard notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_dashboard_shared(self, user_id: str, *, name: str, shared_by: str) -> None:
        """Notify that a dashboard was shared with someone."""
        await self._send(
            user_id=user_id,
            subject=f"A dashboard was shared with you: {name}",
            body=f"{shared_by} shared the dashboard {name!r} with you.",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_layout_updated(self, user_id: str, *, name: str) -> None:
        """Notify that a shared dashboard's layout changed."""
        await self._send(
            user_id=user_id,
            subject=f"Dashboard layout updated: {name}",
            body=f"The layout of {name!r} has been changed.",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_widget_failure(
        self, user_id: str, *, name: str, widget: str, reason: str
    ) -> None:
        """Notify that a widget failed to resolve."""
        await self._send(
            user_id=user_id,
            subject=f"A dashboard widget failed: {name}",
            body=f"Widget {widget!r} on {name!r} could not load: {reason}",
            notification_type=NotificationType.ERROR,
        )

    async def send_connection_lost(self, user_id: str, *, name: str) -> None:
        """Notify that a real-time connection dropped."""
        await self._send(
            user_id=user_id,
            subject=f"Live updates stopped: {name}",
            body=f"The real-time connection to {name!r} was lost; it will reconnect.",
            notification_type=NotificationType.WARNING,
        )

    async def send_refresh_failure(self, user_id: str, *, name: str, reason: str) -> None:
        """Notify that an automatic refresh failed."""
        await self._send(
            user_id=user_id,
            subject=f"Dashboard refresh failed: {name}",
            body=f"Refreshing {name!r} failed: {reason}",
            notification_type=NotificationType.ERROR,
        )


__all__ = ["DashboardNotificationService"]
