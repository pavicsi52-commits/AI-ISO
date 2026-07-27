"""Tests for :class:`app.notifications.validation_notifications
.ValidationNotificationService`.

Every send must be best-effort -- see
``services/workflow-runtime-service``'s own identical precedent.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from shared_core.exceptions.notification import NotificationError
from shared_core.notifications.manager import NotificationManager

from app.notifications.validation_notifications import ValidationNotificationService

_SEND_CALLS = [
    ("send_validation_started", {"profile_name": "infra-profile"}),
    ("send_validation_completed", {"profile_name": "infra-profile"}),
    ("send_validation_failed", {"profile_name": "infra-profile"}),
    ("send_critical_validation_failed", {"profile_name": "infra-profile"}),
    ("send_compliance_failure", {"profile_name": "infra-profile"}),
    ("send_validation_timeout", {"profile_name": "infra-profile"}),
    ("send_remediation_available", {"profile_name": "infra-profile"}),
]


@pytest.fixture
def manager() -> NotificationManager:
    return AsyncMock(spec=NotificationManager)


@pytest.mark.parametrize(("method_name", "kwargs"), _SEND_CALLS)
async def test_send_methods_forward_to_manager(
    manager: NotificationManager, method_name: str, kwargs: dict[str, object]
) -> None:
    service = ValidationNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)

    manager.send.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.parametrize(("method_name", "kwargs"), _SEND_CALLS)
async def test_send_methods_swallow_notification_error(
    manager: NotificationManager, method_name: str, kwargs: dict[str, object]
) -> None:
    manager.send.side_effect = NotificationError("no channel configured")  # type: ignore[attr-defined]
    service = ValidationNotificationService(manager)

    await getattr(service, method_name)("user-1", **kwargs)


__all__: list[str] = []
