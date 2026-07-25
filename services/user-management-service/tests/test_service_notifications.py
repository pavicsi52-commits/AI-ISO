"""Tests for :class:`app.notifications.user_notifications.UserNotificationService`.

Every send must be best-effort -- see
``services/authentication-service``'s identical precedent, and the real
bug ("registration blocked entirely by a notification failure") that
established it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from shared_core.exceptions.notification import NotificationError
from shared_core.notifications.manager import NotificationManager

from app.notifications.user_notifications import UserNotificationService

_SEND_CALLS = [
    ("send_invitation", {"invite_url": "https://x/accept", "message": None}),
    ("send_invitation_reminder", {"invite_url": "https://x/accept"}),
    ("send_profile_updated", {}),
    ("send_account_activated", {}),
    ("send_account_suspended", {}),
    ("send_account_deleted", {}),
]


@pytest.fixture
def manager() -> NotificationManager:
    return AsyncMock(spec=NotificationManager)


@pytest.mark.parametrize("method_name,kwargs", _SEND_CALLS)
async def test_send_methods_forward_to_manager(
    manager: NotificationManager, method_name: str, kwargs: dict[str, str | None]
) -> None:
    service = UserNotificationService(manager)

    await getattr(service, method_name)("user-1@example.com", **kwargs)

    manager.send.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.parametrize("method_name,kwargs", _SEND_CALLS)
async def test_send_methods_swallow_notification_error(
    manager: NotificationManager, method_name: str, kwargs: dict[str, str | None]
) -> None:
    manager.send.side_effect = NotificationError("no channel configured")  # type: ignore[attr-defined]
    service = UserNotificationService(manager)

    await getattr(service, method_name)("user-1@example.com", **kwargs)
