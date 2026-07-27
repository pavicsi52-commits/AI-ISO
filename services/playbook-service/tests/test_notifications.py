"""Tests for :class:`app.notifications.playbook_notifications
.PlaybookNotificationService`.

Every send must be best-effort -- see
``services/automation-service``'s identical precedent.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from shared_core.exceptions.notification import NotificationError
from shared_core.notifications.manager import NotificationManager

from app.notifications.playbook_notifications import PlaybookNotificationService

_SEND_CALLS = [
    ("send_approval_requested", {"playbook_name": "deploy-web"}),
    ("send_approval_completed", {"playbook_name": "deploy-web", "approved": True}),
    ("send_validation_failed", {"playbook_name": "deploy-web"}),
    ("send_content_published", {"playbook_name": "deploy-web"}),
    ("send_content_deprecated", {"playbook_name": "deploy-web"}),
    ("send_signature_failed", {"playbook_name": "deploy-web"}),
]


@pytest.fixture
def manager() -> NotificationManager:
    return AsyncMock(spec=NotificationManager)


@pytest.mark.parametrize(("method_name", "kwargs"), _SEND_CALLS)
async def test_send_methods_forward_to_manager(
    manager: NotificationManager, method_name: str, kwargs: dict[str, object]
) -> None:
    service = PlaybookNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)

    manager.send.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.parametrize(("method_name", "kwargs"), _SEND_CALLS)
async def test_send_methods_swallow_notification_error(
    manager: NotificationManager, method_name: str, kwargs: dict[str, object]
) -> None:
    manager.send.side_effect = NotificationError("no channel configured")  # type: ignore[attr-defined]
    service = PlaybookNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)


__all__: list[str] = []
