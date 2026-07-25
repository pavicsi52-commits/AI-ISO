"""Tests for :class:`app.services.notifications.AuthNotificationService`.

Covers the "every send is best-effort" contract this module exists
for: a :class:`~shared_core.exceptions.notification.NotificationError`
from the underlying :class:`~shared_core.notifications.manager
.NotificationManager` must never propagate out of any ``send_*``
method -- this is the exact bug real smoke-testing caught during this
service's development (registration was failing outright because no
email channel is configured in this environment).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from shared_core.exceptions.notification import NotificationError
from shared_core.notifications.manager import NotificationManager

from app.services.notifications import AuthNotificationService

_SEND_CALLS = [
    ("send_welcome", {}),
    ("send_verification_email", {"verification_url": "https://example.com/v"}),
    ("send_password_reset", {"reset_url": "https://example.com/r"}),
    ("send_mfa_enabled", {}),
    ("send_login_alert", {"ip_address": "1.2.3.4"}),
    ("send_suspicious_login", {"ip_address": "1.2.3.4"}),
    ("send_account_locked", {}),
    ("send_password_changed", {}),
]


@pytest.fixture
def manager() -> NotificationManager:
    return AsyncMock(spec=NotificationManager)


@pytest.mark.parametrize("method_name,kwargs", _SEND_CALLS)
async def test_send_methods_forward_to_manager(
    manager: NotificationManager, method_name: str, kwargs: dict[str, str]
) -> None:
    service = AuthNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)

    manager.send.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.parametrize("method_name,kwargs", _SEND_CALLS)
async def test_send_methods_swallow_notification_error(
    manager: NotificationManager, method_name: str, kwargs: dict[str, str]
) -> None:
    manager.send.side_effect = NotificationError("no channel configured")  # type: ignore[attr-defined]
    service = AuthNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)
