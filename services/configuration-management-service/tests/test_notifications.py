"""Tests for :class:`app.notifications.configuration_notifications
.ConfigurationNotificationService`.

Every send must be best-effort -- see
``services/asset-management-service``'s identical precedent.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from shared_core.exceptions.notification import NotificationError
from shared_core.notifications.manager import NotificationManager

from app.notifications.configuration_notifications import ConfigurationNotificationService

_SEND_CALLS = [
    ("send_approval_requested", {"profile_name": "web-tier"}),
    ("send_approval_completed", {"profile_name": "web-tier", "approved": True}),
    ("send_drift_detected", {"profile_name": "web-tier"}),
    ("send_compliance_failure", {"profile_name": "web-tier"}),
    ("send_backup_completed", {"profile_name": "web-tier"}),
    ("send_restore_completed", {"profile_name": "web-tier"}),
    ("send_rollback_completed", {"profile_name": "web-tier"}),
]


@pytest.fixture
def manager() -> NotificationManager:
    return AsyncMock(spec=NotificationManager)


@pytest.mark.parametrize(("method_name", "kwargs"), _SEND_CALLS)
async def test_send_methods_forward_to_manager(
    manager: NotificationManager, method_name: str, kwargs: dict[str, object]
) -> None:
    service = ConfigurationNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)

    manager.send.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.parametrize(("method_name", "kwargs"), _SEND_CALLS)
async def test_send_methods_swallow_notification_error(
    manager: NotificationManager, method_name: str, kwargs: dict[str, object]
) -> None:
    manager.send.side_effect = NotificationError("no channel configured")  # type: ignore[attr-defined]
    service = ConfigurationNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)


__all__: list[str] = []
