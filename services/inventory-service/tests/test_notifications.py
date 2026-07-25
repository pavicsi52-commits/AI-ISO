"""Tests for :class:`app.notifications.inventory_notifications.InventoryNotificationService`.

Every send must be best-effort -- see ``services/project-service``'s
identical precedent.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from shared_core.exceptions.notification import NotificationError
from shared_core.notifications.manager import NotificationManager

from app.notifications.inventory_notifications import InventoryNotificationService

_SEND_CALLS = [
    ("send_asset_offline", {"asset_name": "web-01"}),
    ("send_health_changed", {"asset_name": "web-01", "health_status": "warning"}),
    ("send_duplicate_detected", {"asset_name": "web-01", "identifier": "web-01.internal"}),
    ("send_import_completed", {"succeeded_rows": 5}),
    ("send_import_failed", {"error_message": "bad file"}),
    ("send_topology_changed", {"asset_name": "web-01"}),
    ("send_critical_asset_updated", {"asset_name": "web-01"}),
]


@pytest.fixture
def manager() -> NotificationManager:
    return AsyncMock(spec=NotificationManager)


@pytest.mark.parametrize(("method_name", "kwargs"), _SEND_CALLS)
async def test_send_methods_forward_to_manager(
    manager: NotificationManager, method_name: str, kwargs: dict[str, object]
) -> None:
    service = InventoryNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)

    manager.send.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.parametrize(("method_name", "kwargs"), _SEND_CALLS)
async def test_send_methods_swallow_notification_error(
    manager: NotificationManager, method_name: str, kwargs: dict[str, object]
) -> None:
    manager.send.side_effect = NotificationError("no channel configured")  # type: ignore[attr-defined]
    service = InventoryNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)


__all__: list[str] = []
