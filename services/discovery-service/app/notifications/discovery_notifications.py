"""Discovery notifications.

Per docs/037 "NOTIFICATIONS": Discovery Started, Discovery Completed,
Discovery Failed, Critical Asset Found, Duplicate Assets, Topology
Changed, Scan Timeout, Credential Failure. "Integrate Prompt 025." Thin
wrapper over :class:`shared_core.notifications.manager.NotificationManager`,
the same best-effort ``_send()`` pattern every prior AI-IOS service's
own notification service established -- a notification failure never
blocks the triggering operation.
"""

from __future__ import annotations

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.exceptions.notification import NotificationError
from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager

logger = get_logger("app.notifications.discovery_notifications")


class DiscoveryNotificationService:
    """Sends every discovery-related notification this service triggers, best-effort."""

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
                "Failed to send discovery notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_discovery_started(self, user_id: str, *, job_id: str) -> None:
        """Notify *user_id* a discovery job started ("Discovery Started")."""
        await self._send(
            user_id=user_id,
            body=f"Discovery job '{job_id}' has started.",
            subject="An AI-IOS discovery job started",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_discovery_completed(
        self, user_id: str, *, job_id: str, discovered_asset_count: int
    ) -> None:
        """Notify *user_id* a discovery job completed ("Discovery Completed")."""
        await self._send(
            user_id=user_id,
            body=f"Discovery job '{job_id}' completed: {discovered_asset_count} asset(s) found.",
            subject="An AI-IOS discovery job completed",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_discovery_failed(self, user_id: str, *, job_id: str, error_message: str) -> None:
        """Notify *user_id* a discovery job failed ("Discovery Failed")."""
        await self._send(
            user_id=user_id,
            body=f"Discovery job '{job_id}' failed: {error_message}",
            subject="An AI-IOS discovery job failed",
            notification_type=NotificationType.CRITICAL,
        )

    async def send_critical_asset_found(self, user_id: str, *, asset_name: str) -> None:
        """Notify *user_id* a critical asset was found ("Critical Asset Found")."""
        await self._send(
            user_id=user_id,
            body=f"A critical asset '{asset_name}' was discovered.",
            subject="A critical asset was discovered",
            notification_type=NotificationType.WARNING,
        )

    async def send_duplicate_assets(self, user_id: str, *, identifier: str) -> None:
        """Notify *user_id* duplicate assets were detected ("Duplicate Assets")."""
        await self._send(
            user_id=user_id,
            body=f"Duplicate assets were detected for identifier {identifier!r}.",
            subject="Duplicate assets detected during discovery",
            notification_type=NotificationType.WARNING,
        )

    async def send_topology_changed(self, user_id: str, *, job_id: str) -> None:
        """Notify *user_id* discovery updated the known topology ("Topology Changed")."""
        await self._send(
            user_id=user_id,
            body=f"Discovery job '{job_id}' updated the known asset topology.",
            subject="AI-IOS asset topology changed",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_scan_timeout(self, user_id: str, *, address: str) -> None:
        """Notify *user_id* a probe timed out ("Scan Timeout")."""
        await self._send(
            user_id=user_id,
            body=f"A discovery probe against '{address}' timed out.",
            subject="An AI-IOS discovery probe timed out",
            notification_type=NotificationType.WARNING,
        )

    async def send_credential_failure(self, user_id: str, *, address: str) -> None:
        """Notify *user_id* a credential failed authentication ("Credential Failure")."""
        await self._send(
            user_id=user_id,
            body=f"Authentication failed while discovering '{address}'.",
            subject="An AI-IOS discovery credential failed",
            notification_type=NotificationType.WARNING,
        )


__all__ = ["DiscoveryNotificationService"]
