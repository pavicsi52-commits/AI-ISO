"""Tests for :class:`app.notifications.workflow_notifications
.WorkflowNotificationService`.

Every send must be best-effort -- see
``services/automation-service``'s identical precedent.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from shared_core.exceptions.notification import NotificationError
from shared_core.notifications.manager import NotificationManager

from app.notifications.workflow_notifications import WorkflowNotificationService

_SEND_CALLS = [
    ("send_workflow_started", {"workflow_name": "deploy-web"}),
    ("send_workflow_completed", {"workflow_name": "deploy-web"}),
    ("send_workflow_failed", {"workflow_name": "deploy-web"}),
    ("send_approval_required", {"workflow_name": "deploy-web"}),
    ("send_timeout", {"workflow_name": "deploy-web"}),
    ("send_rollback_completed", {"workflow_name": "deploy-web"}),
    ("send_replay_completed", {"workflow_name": "deploy-web"}),
]


@pytest.fixture
def manager() -> NotificationManager:
    return AsyncMock(spec=NotificationManager)


@pytest.mark.parametrize(("method_name", "kwargs"), _SEND_CALLS)
async def test_send_methods_forward_to_manager(
    manager: NotificationManager, method_name: str, kwargs: dict[str, object]
) -> None:
    service = WorkflowNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)

    manager.send.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.parametrize(("method_name", "kwargs"), _SEND_CALLS)
async def test_send_methods_swallow_notification_error(
    manager: NotificationManager, method_name: str, kwargs: dict[str, object]
) -> None:
    manager.send.side_effect = NotificationError("no channel configured")  # type: ignore[attr-defined]
    service = WorkflowNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)


__all__: list[str] = []
