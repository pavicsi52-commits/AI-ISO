"""Tests for :class:`app.notifications.project_notifications.ProjectNotificationService`.

Every send must be best-effort -- see ``services/rbac-service``'s
identical precedent, and the real bug ("registration blocked entirely
by a notification failure") that originally established it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from shared_core.exceptions.notification import NotificationError
from shared_core.notifications.manager import NotificationManager

from app.notifications.project_notifications import ProjectNotificationService

_SEND_CALLS = [
    ("send_project_created", {"project_name": "Acme Plant"}),
    ("send_invitation_sent", {"project_name": "Acme Plant"}),
    ("send_invitation_accepted", {"member_name": "Jane"}),
    ("send_ownership_changed", {"project_name": "Acme Plant"}),
    ("send_project_archived", {"project_name": "Acme Plant"}),
    ("send_project_restored", {"project_name": "Acme Plant"}),
    ("send_project_deleted", {"project_name": "Acme Plant"}),
]


@pytest.fixture
def manager() -> NotificationManager:
    return AsyncMock(spec=NotificationManager)


@pytest.mark.parametrize("method_name,kwargs", _SEND_CALLS)
async def test_send_methods_forward_to_manager(
    manager: NotificationManager, method_name: str, kwargs: dict[str, str]
) -> None:
    service = ProjectNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)

    manager.send.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.parametrize("method_name,kwargs", _SEND_CALLS)
async def test_send_methods_swallow_notification_error(
    manager: NotificationManager, method_name: str, kwargs: dict[str, str]
) -> None:
    manager.send.side_effect = NotificationError("no channel configured")  # type: ignore[attr-defined]
    service = ProjectNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)
