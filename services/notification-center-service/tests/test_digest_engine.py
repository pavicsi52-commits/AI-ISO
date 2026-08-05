"""Pure tests for app/digest/engine.py -- no database, no fixtures."""

from __future__ import annotations

import pytest
from shared_core.enums.notification_channel import NotificationChannel
from shared_core.notifications.delivery import DeliveryStatus

from app.digest.engine import build_user_digest, render_digest_body, to_shared_message
from app.models.enums import (
    NotificationCategory,
    NotificationPriority,
    to_shared_notification_type,
    to_shared_priority,
)

pytestmark = pytest.mark.asyncio


class TestToSharedMessage:
    async def test_channel_is_always_in_app_regardless_of_category(self) -> None:
        message = to_shared_message(
            notification_id="n1",
            category=NotificationCategory.ALERT,
            priority=NotificationPriority.NORMAL,
            subject="Subj",
            body="Body",
            user_id="u1",
        )
        assert message.channel == NotificationChannel.IN_APP

    async def test_notification_type_is_translated_from_category(self) -> None:
        message = to_shared_message(
            notification_id="n1",
            category=NotificationCategory.FAILURE,
            priority=NotificationPriority.NORMAL,
            subject=None,
            body="Body",
            user_id="u1",
        )
        assert message.notification_type == to_shared_notification_type(
            NotificationCategory.FAILURE
        )

    async def test_priority_is_translated(self) -> None:
        message = to_shared_message(
            notification_id="n1",
            category=NotificationCategory.ALERT,
            priority=NotificationPriority.HIGH,
            subject=None,
            body="Body",
            user_id="u1",
        )
        assert message.priority == to_shared_priority(NotificationPriority.HIGH)

    async def test_status_is_always_pending(self) -> None:
        message = to_shared_message(
            notification_id="n1",
            category=NotificationCategory.ALERT,
            priority=NotificationPriority.NORMAL,
            subject=None,
            body="Body",
            user_id="u1",
        )
        assert message.status == DeliveryStatus.PENDING

    async def test_carries_through_notification_id_subject_body_and_user_id(self) -> None:
        message = to_shared_message(
            notification_id="n42",
            category=NotificationCategory.INFORMATION,
            priority=NotificationPriority.LOW,
            subject="Hello",
            body="World",
            user_id="u99",
        )
        assert message.notification_id == "n42"
        assert message.subject == "Hello"
        assert message.body == "World"
        assert message.user_id == "u99"


class TestBuildUserDigest:
    async def test_duplicate_messages_are_deduplicated(self) -> None:
        first = to_shared_message(
            notification_id="n1",
            category=NotificationCategory.ALERT,
            priority=NotificationPriority.NORMAL,
            subject="Disk full",
            body="body",
            user_id="u1",
        )
        duplicate = to_shared_message(
            notification_id="n2",
            category=NotificationCategory.ALERT,
            priority=NotificationPriority.NORMAL,
            subject="Disk full",
            body="body",
            user_id="u1",
        )
        digest = build_user_digest("u1", [first, duplicate], max_items=10)
        assert digest.total_count == 1

    async def test_respects_the_max_items_cap(self) -> None:
        messages = [
            to_shared_message(
                notification_id=f"n{i}",
                category=NotificationCategory.ALERT,
                priority=NotificationPriority.NORMAL,
                subject=f"Subject {i}",
                body=f"body {i}",
                user_id="u1",
            )
            for i in range(5)
        ]
        digest = build_user_digest("u1", messages, max_items=2)
        assert digest.total_count == 2

    async def test_distinct_messages_are_not_deduplicated(self) -> None:
        first = to_shared_message(
            notification_id="n1",
            category=NotificationCategory.ALERT,
            priority=NotificationPriority.NORMAL,
            subject="Subject A",
            body="body A",
            user_id="u1",
        )
        second = to_shared_message(
            notification_id="n2",
            category=NotificationCategory.ALERT,
            priority=NotificationPriority.NORMAL,
            subject="Subject B",
            body="body B",
            user_id="u1",
        )
        digest = build_user_digest("u1", [first, second], max_items=10)
        assert digest.total_count == 2


class TestRenderDigestBody:
    async def test_empty_digest_reports_no_new_notifications(self) -> None:
        digest = build_user_digest("u1", [], max_items=10)
        assert render_digest_body(digest) == "No new notifications."

    async def test_single_group_single_message_body(self) -> None:
        message = to_shared_message(
            notification_id="n1",
            category=NotificationCategory.ALERT,
            priority=NotificationPriority.NORMAL,
            subject="Disk full",
            body="body",
            user_id="u1",
        )
        digest = build_user_digest("u1", [message], max_items=10)
        expected = "You have 1 new notification(s):\n\n## Warning\n- Disk full"
        assert render_digest_body(digest) == expected

    async def test_falls_back_to_body_when_subject_is_missing(self) -> None:
        message = to_shared_message(
            notification_id="n1",
            category=NotificationCategory.INFORMATION,
            priority=NotificationPriority.NORMAL,
            subject=None,
            body="just body text",
            user_id="u1",
        )
        digest = build_user_digest("u1", [message], max_items=10)
        expected = "You have 1 new notification(s):\n\n## Information\n- just body text"
        assert render_digest_body(digest) == expected

    async def test_multiple_groups_are_separated_by_a_blank_line_with_no_trailing_blank(
        self,
    ) -> None:
        alert_message = to_shared_message(
            notification_id="n1",
            category=NotificationCategory.ALERT,
            priority=NotificationPriority.NORMAL,
            subject="Disk full",
            body="body1",
            user_id="u1",
        )
        success_message = to_shared_message(
            notification_id="n2",
            category=NotificationCategory.SUCCESS,
            priority=NotificationPriority.NORMAL,
            subject="Deploy ok",
            body="body2",
            user_id="u1",
        )
        digest = build_user_digest("u1", [alert_message, success_message], max_items=10)
        expected = (
            "You have 2 new notification(s):\n"
            "\n"
            "## Warning\n"
            "- Disk full\n"
            "\n"
            "## Success\n"
            "- Deploy ok"
        )
        result = render_digest_body(digest)
        assert result == expected
        assert not result.endswith("\n")

    async def test_multiple_messages_within_one_group_each_get_a_bullet_line(self) -> None:
        first = to_shared_message(
            notification_id="n1",
            category=NotificationCategory.ALERT,
            priority=NotificationPriority.NORMAL,
            subject="First alert",
            body="body1",
            user_id="u1",
        )
        second = to_shared_message(
            notification_id="n2",
            category=NotificationCategory.ALERT,
            priority=NotificationPriority.NORMAL,
            subject="Second alert",
            body="body2",
            user_id="u1",
        )
        digest = build_user_digest("u1", [first, second], max_items=10)
        expected = "You have 2 new notification(s):\n\n## Warning\n- First alert\n- Second alert"
        assert render_digest_body(digest) == expected
