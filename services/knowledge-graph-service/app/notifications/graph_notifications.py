"""Knowledge graph notifications.

Per docs/049 "NOTIFICATIONS": Synchronization Failed, Graph Import
Failed, Graph Export Completed, Snapshot Completed, Critical
Relationship Change.

A thin wrapper over ``shared_core``'s notification manager using the
best-effort ``_send`` pattern every prior AI-IOS service established:
**a notification failure never blocks the operation that triggered
it.** A synchronization that completed correctly must not report an
error because an SMTP server was down.
"""

from __future__ import annotations

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.exceptions.notification import NotificationError
from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager

logger = get_logger("app.notifications.graph_notifications")


class GraphNotificationService:
    """Sends every knowledge-graph notification, best-effort."""

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
                "Failed to send a knowledge-graph notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_sync_failed(self, user_id: str, *, source: str, reason: str) -> None:
        """Notify that a source failed to synchronize."""
        await self._send(
            user_id=user_id,
            subject=f"Graph synchronization failed: {source}",
            body=f"Synchronizing {source!r} into the knowledge graph failed: {reason}",
            notification_type=NotificationType.ERROR,
        )

    async def send_import_failed(self, user_id: str, *, filename: str, reason: str) -> None:
        """Notify that a graph import failed."""
        await self._send(
            user_id=user_id,
            subject=f"Graph import failed: {filename}",
            body=f"Importing {filename!r} into the knowledge graph failed: {reason}",
            notification_type=NotificationType.ERROR,
        )

    async def send_export_completed(self, user_id: str, *, filename: str, node_count: int) -> None:
        """Notify that a graph export finished."""
        await self._send(
            user_id=user_id,
            subject=f"Graph export ready: {filename}",
            body=f"{filename!r} is ready, containing {node_count:,} nodes.",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_snapshot_completed(self, user_id: str, *, label: str, node_count: int) -> None:
        """Notify that a snapshot finished."""
        await self._send(
            user_id=user_id,
            subject=f"Graph snapshot captured: {label}",
            body=f"Snapshot {label!r} captured {node_count:,} nodes.",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_critical_relationship_change(
        self, user_id: str, *, node_key: str, detail: str
    ) -> None:
        """Notify that a relationship on a critical node changed.

        Sent as a warning rather than information: a dependency edge
        appearing or vanishing on something declared critical is the
        kind of change someone wants to know about before an incident,
        not after.
        """
        await self._send(
            user_id=user_id,
            subject=f"Critical relationship change: {node_key}",
            body=f"A relationship on {node_key!r} changed: {detail}",
            notification_type=NotificationType.WARNING,
        )


__all__ = ["GraphNotificationService"]
