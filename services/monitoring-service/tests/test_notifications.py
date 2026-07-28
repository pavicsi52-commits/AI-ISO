"""Tests for :class:`app.notifications.monitoring_notifications
.MonitoringNotificationService`.

Every send must be best-effort -- see
``services/validation-service``'s own identical precedent.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from shared_core.exceptions.notification import NotificationError
from shared_core.notifications.manager import NotificationManager

from app.notifications.monitoring_notifications import MonitoringNotificationService

_SEND_CALLS = [
    ("send_critical_health_change", {"target_name": "server-1"}),
    ("send_availability_issue", {"target_name": "server-1"}),
    ("send_synthetic_failure", {"test_name": "ping-check"}),
    ("send_threshold_exceeded", {"metric_name": "cpu_usage_percent"}),
    ("send_capacity_warning", {"target_name": "server-1"}),
    ("send_monitoring_failure", {"collector_name": "connectivity-collector"}),
]


@pytest.fixture
def manager() -> NotificationManager:
    return AsyncMock(spec=NotificationManager)


@pytest.mark.parametrize(("method_name", "kwargs"), _SEND_CALLS)
async def test_send_methods_forward_to_manager(
    manager: NotificationManager, method_name: str, kwargs: dict[str, object]
) -> None:
    service = MonitoringNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)

    manager.send.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.parametrize(("method_name", "kwargs"), _SEND_CALLS)
async def test_send_methods_swallow_notification_error(
    manager: NotificationManager, method_name: str, kwargs: dict[str, object]
) -> None:
    manager.send.side_effect = NotificationError("no channel configured")  # type: ignore[attr-defined]
    service = MonitoringNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)


__all__: list[str] = []
