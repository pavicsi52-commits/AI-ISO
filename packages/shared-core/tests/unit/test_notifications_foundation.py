"""Tests for priority.py, attachments.py, delivery.py, channels.py, and exceptions.py."""

from __future__ import annotations

import pytest
from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.enums.priority import Priority
from shared_core.notifications.attachments import (
    Attachment,
    AttachmentKind,
    kind_from_filename,
    scan_attachment,
    validate_attachment_size,
)
from shared_core.notifications.channels import (
    Channel,
    ChannelRegistry,
    NotificationMessage,
    build_notification,
    new_notification_id,
)
from shared_core.notifications.delivery import (
    DeliveryMode,
    DeliveryResult,
    DeliveryStatus,
    build_delivery_result,
)
from shared_core.notifications.exceptions import (
    AttachmentTooLargeError,
    ChannelUnavailableError,
)
from shared_core.notifications.priority import priority_rank, sort_by_priority

# --- priority.py ---


def test_priority_rank_orders_critical_before_background() -> None:
    assert priority_rank(Priority.CRITICAL) < priority_rank(Priority.BACKGROUND)


def test_sort_by_priority_orders_most_urgent_first() -> None:
    result = sort_by_priority([Priority.LOW, Priority.CRITICAL, Priority.NORMAL])

    assert result == [Priority.CRITICAL, Priority.NORMAL, Priority.LOW]


# --- attachments.py ---


def test_kind_from_filename_recognizes_every_documented_extension() -> None:
    assert kind_from_filename("report.pdf") == AttachmentKind.PDF
    assert kind_from_filename("data.csv") == AttachmentKind.CSV
    assert kind_from_filename("notes.txt") == AttachmentKind.TXT
    assert kind_from_filename("payload.json") == AttachmentKind.JSON
    assert kind_from_filename("archive.zip") == AttachmentKind.ZIP
    assert kind_from_filename("photo.PNG") == AttachmentKind.IMAGE


def test_kind_from_filename_returns_none_for_unrecognized_extensions() -> None:
    assert kind_from_filename("binary.exe") is None
    assert kind_from_filename("no-extension") is None


def test_validate_attachment_size_passes_under_the_limit() -> None:
    attachment = Attachment(
        filename="x.txt", content_type="text/plain", kind=AttachmentKind.TXT, data=b"hi"
    )

    validate_attachment_size(attachment, max_bytes=100)


def test_validate_attachment_size_raises_over_the_limit() -> None:
    attachment = Attachment(
        filename="x.txt", content_type="text/plain", kind=AttachmentKind.TXT, data=b"x" * 10
    )

    with pytest.raises(AttachmentTooLargeError):
        validate_attachment_size(attachment, max_bytes=5)


async def test_scan_attachment_passes_through_when_no_hook_is_configured() -> None:
    attachment = Attachment(
        filename="x.txt", content_type="text/plain", kind=AttachmentKind.TXT, data=b"hi"
    )

    assert await scan_attachment(attachment) is True


async def test_scan_attachment_calls_the_configured_hook() -> None:
    attachment = Attachment(
        filename="x.txt", content_type="text/plain", kind=AttachmentKind.TXT, data=b"hi"
    )

    async def _reject(_attachment: Attachment) -> bool:
        return False

    assert await scan_attachment(attachment, hook=_reject) is False


# --- delivery.py ---


def test_build_delivery_result_stamps_the_current_time() -> None:
    result = build_delivery_result(status=DeliveryStatus.SENT, channel=NotificationChannel.EMAIL)

    assert result.status == DeliveryStatus.SENT
    assert result.channel == NotificationChannel.EMAIL
    assert result.completed_at is not None


def test_delivery_mode_covers_every_documented_mode() -> None:
    expected = {"immediate", "scheduled", "recurring", "delayed", "bulk", "broadcast", "multicast"}
    assert {mode.value for mode in DeliveryMode} == expected


# --- channels.py ---


def test_new_notification_id_generates_unique_ids() -> None:
    assert new_notification_id() != new_notification_id()


def test_build_notification_defaults_to_normal_priority_and_pending_status() -> None:
    message = build_notification(
        channel=NotificationChannel.EMAIL, notification_type=NotificationType.INFORMATION, body="hi"
    )

    assert message.priority == Priority.NORMAL
    assert message.status == DeliveryStatus.PENDING
    assert message.notification_id


def test_build_notification_accepts_extra_message_fields() -> None:
    message = build_notification(
        channel=NotificationChannel.SLACK,
        notification_type=NotificationType.CRITICAL,
        body="disk full",
        user_id="user-1",
        subject="Disk Alert",
    )

    assert message.user_id == "user-1"
    assert message.subject == "Disk Alert"


class _StubChannel:
    channel_type = NotificationChannel.WEBHOOK

    async def send(self, message: NotificationMessage) -> DeliveryResult:
        return build_delivery_result(status=DeliveryStatus.SENT, channel=self.channel_type)


def test_stub_channel_satisfies_the_channel_protocol() -> None:
    assert isinstance(_StubChannel(), Channel)


def test_channel_registry_register_and_get_roundtrips() -> None:
    registry = ChannelRegistry()
    channel = _StubChannel()

    registry.register(channel)

    assert registry.get(NotificationChannel.WEBHOOK) is channel
    assert registry.is_registered(NotificationChannel.WEBHOOK) is True
    assert registry.registered_channels() == [NotificationChannel.WEBHOOK]


def test_channel_registry_get_raises_for_an_unregistered_channel() -> None:
    with pytest.raises(ChannelUnavailableError):
        ChannelRegistry().get(NotificationChannel.SMS)


def test_channel_registry_is_registered_is_false_for_an_unregistered_channel() -> None:
    assert ChannelRegistry().is_registered(NotificationChannel.SMS) is False
