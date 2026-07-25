"""Tests for :class:`app.notifications.organization_notifications.OrganizationNotificationService`.

Every send must be best-effort -- see
``services/rbac-service``'s identical precedent, and the real bug
("registration blocked entirely by a notification failure") that
originally established it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from shared_core.exceptions.notification import NotificationError
from shared_core.notifications.manager import NotificationManager

from app.notifications.organization_notifications import OrganizationNotificationService

_SEND_CALLS = [
    ("send_organization_created", {"organization_name": "Acme Corp"}),
    ("send_invitation", {"invite_url": "http://test/accept?token=abc", "message": None}),
    ("send_invitation_reminder", {"invite_url": "http://test/accept?token=abc"}),
    ("send_subscription_expiring", {"days_remaining": 3}),
    ("send_license_expiring", {"days_remaining": 5}),
    ("send_quota_warning", {"quota_name": "max_users"}),
    ("send_quota_exceeded", {"quota_name": "max_users"}),
    ("send_organization_suspended", {"reason": "non-payment"}),
]


@pytest.fixture
def manager() -> NotificationManager:
    return AsyncMock(spec=NotificationManager)


@pytest.mark.parametrize("method_name,kwargs", _SEND_CALLS)
async def test_send_methods_forward_to_manager(
    manager: NotificationManager, method_name: str, kwargs: dict[str, object]
) -> None:
    service = OrganizationNotificationService(manager)

    recipient = "invitee@example.com" if method_name == "send_invitation" else "user-1"
    await getattr(service, method_name)(recipient, **kwargs)

    manager.send.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.parametrize("method_name,kwargs", _SEND_CALLS)
async def test_send_methods_swallow_notification_error(
    manager: NotificationManager, method_name: str, kwargs: dict[str, object]
) -> None:
    manager.send.side_effect = NotificationError("no channel configured")  # type: ignore[attr-defined]
    service = OrganizationNotificationService(manager)

    recipient = "invitee@example.com" if method_name == "send_invitation" else "user-1"
    await getattr(service, method_name)(recipient, **kwargs)


async def test_send_invitation_prepends_custom_message(manager: NotificationManager) -> None:
    service = OrganizationNotificationService(manager)
    await service.send_invitation(
        "invitee@example.com", invite_url="http://test/accept", message="Welcome aboard!"
    )
    _, kwargs = manager.send.call_args  # type: ignore[attr-defined]
    assert "Welcome aboard!" in kwargs["body"]
