"""Tests for :class:`app.notifications.discovery_notifications
.DiscoveryNotificationService`.

Every send must be best-effort -- see
``services/inventory-service``'s identical precedent.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from shared_core.exceptions.notification import NotificationError
from shared_core.notifications.manager import NotificationManager

from app.notifications.discovery_notifications import DiscoveryNotificationService

_SEND_CALLS = [
    ("send_discovery_started", {"job_id": "job-1"}),
    ("send_discovery_completed", {"job_id": "job-1", "discovered_asset_count": 3}),
    ("send_discovery_failed", {"job_id": "job-1", "error_message": "unreachable"}),
    ("send_critical_asset_found", {"asset_name": "core-router"}),
    ("send_duplicate_assets", {"identifier": "192.0.2.1"}),
    ("send_topology_changed", {"job_id": "job-1"}),
    ("send_scan_timeout", {"address": "192.0.2.1"}),
    ("send_credential_failure", {"address": "192.0.2.1"}),
]


@pytest.fixture
def manager() -> NotificationManager:
    return AsyncMock(spec=NotificationManager)


@pytest.mark.parametrize(("method_name", "kwargs"), _SEND_CALLS)
async def test_send_methods_forward_to_manager(
    manager: NotificationManager, method_name: str, kwargs: dict[str, object]
) -> None:
    service = DiscoveryNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)

    manager.send.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.parametrize(("method_name", "kwargs"), _SEND_CALLS)
async def test_send_methods_swallow_notification_error(
    manager: NotificationManager, method_name: str, kwargs: dict[str, object]
) -> None:
    manager.send.side_effect = NotificationError("no channel configured")  # type: ignore[attr-defined]
    service = DiscoveryNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)


__all__: list[str] = []
