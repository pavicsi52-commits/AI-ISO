"""Asset management notifications.

Per docs/038 "NOTIFICATIONS": Warranty Expiring, Contract Expiring,
Maintenance Due, Maintenance Completed, Risk Increased, Compliance
Failure, Asset Retirement, Ownership Changed. "Integrate Prompt 025."
Thin wrapper over :class:`shared_core.notifications.manager
.NotificationManager`, the same best-effort ``_send()`` pattern every
prior AI-IOS service's own notification service established -- a
notification failure never blocks the triggering operation.
"""

from __future__ import annotations

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.exceptions.notification import NotificationError
from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager

logger = get_logger("app.notifications.asset_notifications")


class AssetNotificationService:
    """Sends every asset-management-related notification this service triggers, best-effort."""

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
                "Failed to send asset management notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_warranty_expiring(self, user_id: str, *, business_name: str) -> None:
        """Notify *user_id* a managed asset's warranty is expiring soon ("Warranty Expiring")."""
        await self._send(
            user_id=user_id,
            body=f"The warranty for '{business_name}' is expiring soon.",
            subject="An AI-IOS asset warranty is expiring",
            notification_type=NotificationType.WARNING,
        )

    async def send_contract_expiring(self, user_id: str, *, business_name: str) -> None:
        """Notify *user_id* a managed asset's contract is expiring soon ("Contract Expiring")."""
        await self._send(
            user_id=user_id,
            body=f"A contract covering '{business_name}' is expiring soon.",
            subject="An AI-IOS asset contract is expiring",
            notification_type=NotificationType.WARNING,
        )

    async def send_maintenance_due(self, user_id: str, *, business_name: str) -> None:
        """Notify *user_id* a maintenance activity is due ("Maintenance Due")."""
        await self._send(
            user_id=user_id,
            body=f"Maintenance for '{business_name}' is due.",
            subject="AI-IOS asset maintenance is due",
            notification_type=NotificationType.MAINTENANCE,
        )

    async def send_maintenance_completed(self, user_id: str, *, business_name: str) -> None:
        """Notify *user_id* a maintenance activity completed ("Maintenance Completed")."""
        await self._send(
            user_id=user_id,
            body=f"Maintenance for '{business_name}' has completed.",
            subject="AI-IOS asset maintenance completed",
            notification_type=NotificationType.MAINTENANCE,
        )

    async def send_risk_increased(
        self, user_id: str, *, business_name: str, risk_score: float
    ) -> None:
        """Notify *user_id* a managed asset's risk score increased ("Risk Increased")."""
        await self._send(
            user_id=user_id,
            body=f"The risk score for '{business_name}' increased to {risk_score}.",
            subject="An AI-IOS asset risk score increased",
            notification_type=NotificationType.WARNING,
        )

    async def send_compliance_failure(self, user_id: str, *, business_name: str) -> None:
        """Notify *user_id* a compliance evaluation failed ("Compliance Failure")."""
        await self._send(
            user_id=user_id,
            body=f"A compliance evaluation failed for '{business_name}'.",
            subject="An AI-IOS asset failed compliance",
            notification_type=NotificationType.ERROR,
        )

    async def send_asset_retirement(self, user_id: str, *, business_name: str) -> None:
        """Notify *user_id* a managed asset was retired ("Asset Retirement")."""
        await self._send(
            user_id=user_id,
            body=f"The asset '{business_name}' has been retired.",
            subject="An AI-IOS asset was retired",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_ownership_changed(self, user_id: str, *, business_name: str) -> None:
        """Notify *user_id* a managed asset's ownership changed ("Ownership Changed")."""
        await self._send(
            user_id=user_id,
            body=f"Ownership of '{business_name}' has changed.",
            subject="An AI-IOS asset changed ownership",
            notification_type=NotificationType.INFORMATION,
        )


__all__ = ["AssetNotificationService"]
