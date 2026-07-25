"""Tests for :class:`app.notifications.rbac_notifications.RbacNotificationService`.

Every send must be best-effort -- see
``services/user-management-service``'s identical precedent, and the
real bug ("registration blocked entirely by a notification failure")
that originally established it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from shared_core.exceptions.notification import NotificationError
from shared_core.notifications.manager import NotificationManager

from app.notifications.rbac_notifications import RbacNotificationService

_SEND_CALLS = [
    ("send_role_assigned", {"role_name": "Viewer"}),
    ("send_role_removed", {"role_name": "Viewer"}),
    ("send_permission_changed", {"permission_code": "users:read"}),
    ("send_policy_changed", {"policy_name": "Block Reads"}),
    ("send_unauthorized_access_attempt", {"action": "delete", "resource_type": "users"}),
    ("send_security_violation", {"reason": "impossible travel"}),
]


@pytest.fixture
def manager() -> NotificationManager:
    return AsyncMock(spec=NotificationManager)


@pytest.mark.parametrize("method_name,kwargs", _SEND_CALLS)
async def test_send_methods_forward_to_manager(
    manager: NotificationManager, method_name: str, kwargs: dict[str, str]
) -> None:
    service = RbacNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)

    manager.send.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.parametrize("method_name,kwargs", _SEND_CALLS)
async def test_send_methods_swallow_notification_error(
    manager: NotificationManager, method_name: str, kwargs: dict[str, str]
) -> None:
    manager.send.side_effect = NotificationError("no channel configured")  # type: ignore[attr-defined]
    service = RbacNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)
