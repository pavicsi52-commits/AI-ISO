"""Inventory notifications.

Per docs/036 "NOTIFICATIONS": Asset Offline, Health Changed, Duplicate
Detected, Import Completed, Import Failed, Topology Changed, Critical
Asset Updated. "Integrate Prompt 025." Thin wrapper over
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

logger = get_logger("app.notifications.inventory_notifications")


class InventoryNotificationService:
    """Sends every inventory-related notification this service triggers, best-effort."""

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
                "Failed to send inventory notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_asset_offline(self, user_id: str, *, asset_name: str) -> None:
        """Notify *user_id* an asset went offline ("Asset Offline")."""
        await self._send(
            user_id=user_id,
            body=f"The asset '{asset_name}' is now offline.",
            subject="An AI-IOS asset went offline",
            notification_type=NotificationType.WARNING,
        )

    async def send_health_changed(
        self, user_id: str, *, asset_name: str, health_status: str
    ) -> None:
        """Notify *user_id* an asset's health status changed ("Health Changed")."""
        await self._send(
            user_id=user_id,
            body=f"The asset '{asset_name}' health is now '{health_status}'.",
            subject="An AI-IOS asset health status changed",
            notification_type=NotificationType.WARNING,
        )

    async def send_duplicate_detected(
        self, user_id: str, *, asset_name: str, identifier: str
    ) -> None:
        """Notify *user_id* a duplicate asset identifier was detected
        ("Duplicate Detected")."""
        await self._send(
            user_id=user_id,
            body=f"A duplicate identifier {identifier!r} was detected for asset '{asset_name}'.",
            subject="Duplicate AI-IOS asset identifier detected",
            notification_type=NotificationType.WARNING,
        )

    async def send_import_completed(self, user_id: str, *, succeeded_rows: int) -> None:
        """Notify *user_id* a bulk import finished ("Import Completed")."""
        await self._send(
            user_id=user_id,
            body=f"Your asset import completed: {succeeded_rows} asset(s) created.",
            subject="Your AI-IOS asset import is complete",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_import_failed(self, user_id: str, *, error_message: str) -> None:
        """Notify *user_id* a bulk import failed ("Import Failed")."""
        await self._send(
            user_id=user_id,
            body=f"Your asset import failed: {error_message}",
            subject="Your AI-IOS asset import failed",
            notification_type=NotificationType.CRITICAL,
        )

    async def send_topology_changed(self, user_id: str, *, asset_name: str) -> None:
        """Notify *user_id* an asset's topology relationships changed
        ("Topology Changed")."""
        await self._send(
            user_id=user_id,
            body=f"The topology around asset '{asset_name}' has changed.",
            subject="An AI-IOS asset's topology changed",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_critical_asset_updated(self, user_id: str, *, asset_name: str) -> None:
        """Notify *user_id* a critical asset was updated ("Critical Asset Updated")."""
        await self._send(
            user_id=user_id,
            body=f"The critical asset '{asset_name}' was updated.",
            subject="A critical AI-IOS asset was updated",
            notification_type=NotificationType.WARNING,
        )


__all__ = ["InventoryNotificationService"]
