"""Tests for :class:`app.notifications.asset_notifications.AssetNotificationService`.

Every send must be best-effort -- see ``services/inventory-service``'s
identical precedent.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from shared_core.exceptions.notification import NotificationError
from shared_core.notifications.manager import NotificationManager

from app.notifications.asset_notifications import AssetNotificationService

_SEND_CALLS = [
    ("send_warranty_expiring", {"business_name": "Payments API"}),
    ("send_contract_expiring", {"business_name": "Payments API"}),
    ("send_maintenance_due", {"business_name": "Payments API"}),
    ("send_maintenance_completed", {"business_name": "Payments API"}),
    ("send_risk_increased", {"business_name": "Payments API", "risk_score": 85.0}),
    ("send_compliance_failure", {"business_name": "Payments API"}),
    ("send_asset_retirement", {"business_name": "Payments API"}),
    ("send_ownership_changed", {"business_name": "Payments API"}),
]


@pytest.fixture
def manager() -> NotificationManager:
    return AsyncMock(spec=NotificationManager)


@pytest.mark.parametrize(("method_name", "kwargs"), _SEND_CALLS)
async def test_send_methods_forward_to_manager(
    manager: NotificationManager, method_name: str, kwargs: dict[str, object]
) -> None:
    service = AssetNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)

    manager.send.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.parametrize(("method_name", "kwargs"), _SEND_CALLS)
async def test_send_methods_swallow_notification_error(
    manager: NotificationManager, method_name: str, kwargs: dict[str, object]
) -> None:
    manager.send.side_effect = NotificationError("no channel configured")  # type: ignore[attr-defined]
    service = AssetNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)


__all__: list[str] = []
