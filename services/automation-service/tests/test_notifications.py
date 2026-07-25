"""Tests for :class:`app.notifications.automation_notifications
.AutomationNotificationService`.

Every send must be best-effort -- see
``services/configuration-management-service``'s identical precedent.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from shared_core.exceptions.notification import NotificationError
from shared_core.notifications.manager import NotificationManager

from app.notifications.automation_notifications import AutomationNotificationService

_SEND_CALLS = [
    ("send_execution_started", {"job_name": "deploy-web"}),
    ("send_execution_completed", {"job_name": "deploy-web"}),
    ("send_execution_failed", {"job_name": "deploy-web"}),
    ("send_approval_required", {"job_name": "deploy-web"}),
    ("send_rollback_completed", {"job_name": "deploy-web"}),
    ("send_critical_failure", {"job_name": "deploy-web", "reason": "disk full"}),
    ("send_long_running_job", {"job_name": "deploy-web", "seconds": 120.0}),
    ("send_schedule_missed", {"job_name": "deploy-web"}),
]


@pytest.fixture
def manager() -> NotificationManager:
    return AsyncMock(spec=NotificationManager)


@pytest.mark.parametrize(("method_name", "kwargs"), _SEND_CALLS)
async def test_send_methods_forward_to_manager(
    manager: NotificationManager, method_name: str, kwargs: dict[str, object]
) -> None:
    service = AutomationNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)

    manager.send.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.parametrize(("method_name", "kwargs"), _SEND_CALLS)
async def test_send_methods_swallow_notification_error(
    manager: NotificationManager, method_name: str, kwargs: dict[str, object]
) -> None:
    manager.send.side_effect = NotificationError("no channel configured")  # type: ignore[attr-defined]
    service = AutomationNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)


__all__: list[str] = []
