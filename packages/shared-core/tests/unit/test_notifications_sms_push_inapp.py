"""Tests for sms.py, push.py, and in_app.py."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, ClassVar

import pytest
from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.notifications.channels import build_notification
from shared_core.notifications.delivery import DeliveryStatus
from shared_core.notifications.in_app import InAppChannel, InAppNotificationStore, InAppStatus
from shared_core.notifications.push import PushChannel, build_push_payload
from shared_core.notifications.sms import SmsChannel, build_sms_payload


class _CapturingHandler(BaseHTTPRequestHandler):
    received: ClassVar[list[dict[str, Any]]] = []
    received_headers: ClassVar[list[dict[str, str]]] = []
    response_status = 200

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        type(self).received.append(json.loads(body))
        type(self).received_headers.append(dict(self.headers))
        self.send_response(type(self).response_status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def provider_server() -> Iterator[str]:
    _CapturingHandler.received = []
    _CapturingHandler.received_headers = []
    _CapturingHandler.response_status = 200
    server = HTTPServer(("localhost", 0), _CapturingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://localhost:{server.server_port}/send"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


# --- sms.py ---


def test_build_sms_payload_carries_the_number_and_body() -> None:
    message = build_notification(
        channel=NotificationChannel.SMS,
        notification_type=NotificationType.WARNING,
        body="Low balance",
    )

    payload = build_sms_payload(message, to_number="+15551234567")

    assert payload == {"to": "+15551234567", "body": "Low balance"}


async def test_sms_channel_posts_to_the_provider(provider_server: str) -> None:
    channel = SmsChannel(endpoint=provider_server, phone_number_resolver=lambda _m: "+15551234567")
    message = build_notification(
        channel=NotificationChannel.SMS,
        notification_type=NotificationType.WARNING,
        body="Low balance",
    )

    result = await channel.send(message)

    assert result.status == DeliveryStatus.SENT
    assert _CapturingHandler.received[0]["to"] == "+15551234567"


async def test_sms_channel_reports_failure_on_a_non_2xx_response(provider_server: str) -> None:
    _CapturingHandler.response_status = 400
    channel = SmsChannel(endpoint=provider_server, phone_number_resolver=lambda _m: "+1555")
    message = build_notification(
        channel=NotificationChannel.SMS, notification_type=NotificationType.WARNING, body="x"
    )

    result = await channel.send(message)

    assert result.status == DeliveryStatus.FAILED


async def test_sms_channel_reports_failure_when_unreachable() -> None:
    channel = SmsChannel(
        endpoint="http://localhost:1/send", phone_number_resolver=lambda _m: "+1555"
    )
    message = build_notification(
        channel=NotificationChannel.SMS, notification_type=NotificationType.WARNING, body="x"
    )

    result = await channel.send(message)

    assert result.status == DeliveryStatus.FAILED
    assert result.error is not None


# --- push.py ---


def test_build_push_payload_carries_device_token_title_and_data() -> None:
    message = build_notification(
        channel=NotificationChannel.PUSH,
        notification_type=NotificationType.REMINDER,
        body="Meeting in 5 minutes",
        title="Reminder",
        metadata={"meeting_id": "abc"},
    )

    payload = build_push_payload(message, device_token="tok-123")

    assert payload["to"] == "tok-123"
    assert payload["title"] == "Reminder"
    assert payload["data"] == {"meeting_id": "abc"}


async def test_push_channel_posts_to_the_provider(provider_server: str) -> None:
    channel = PushChannel(endpoint=provider_server, device_token_resolver=lambda _m: "tok-123")
    message = build_notification(
        channel=NotificationChannel.PUSH, notification_type=NotificationType.REMINDER, body="Ping"
    )

    result = await channel.send(message)

    assert result.status == DeliveryStatus.SENT
    assert _CapturingHandler.received[0]["to"] == "tok-123"


async def test_push_channel_reports_failure_when_unreachable() -> None:
    channel = PushChannel(
        endpoint="http://localhost:1/send", device_token_resolver=lambda _m: "tok-123"
    )
    message = build_notification(
        channel=NotificationChannel.PUSH, notification_type=NotificationType.REMINDER, body="Ping"
    )

    result = await channel.send(message)

    assert result.status == DeliveryStatus.FAILED
    assert result.error is not None


# --- in_app.py ---


def test_in_app_store_add_and_list_roundtrips() -> None:
    store = InAppNotificationStore()
    message = build_notification(
        channel=NotificationChannel.IN_APP,
        notification_type=NotificationType.INFORMATION,
        body="Welcome",
        user_id="user-1",
    )

    store.add(message, category="onboarding")

    records = store.list_notifications("user-1")
    assert len(records) == 1
    assert records[0].category == "onboarding"
    assert records[0].in_app_status == InAppStatus.UNREAD


def test_in_app_store_mark_read_and_unread() -> None:
    store = InAppNotificationStore()
    message = build_notification(
        channel=NotificationChannel.IN_APP,
        notification_type=NotificationType.INFORMATION,
        body="Welcome",
        user_id="user-1",
    )
    store.add(message)

    store.mark_read("user-1", message.notification_id)
    assert store.list_notifications("user-1")[0].in_app_status == InAppStatus.READ

    store.mark_unread("user-1", message.notification_id)
    assert store.list_notifications("user-1")[0].in_app_status == InAppStatus.UNREAD


def test_in_app_store_archive() -> None:
    store = InAppNotificationStore()
    message = build_notification(
        channel=NotificationChannel.IN_APP,
        notification_type=NotificationType.INFORMATION,
        body="Welcome",
        user_id="user-1",
    )
    store.add(message)

    store.archive("user-1", message.notification_id)

    assert store.list_notifications("user-1")[0].in_app_status == InAppStatus.ARCHIVED
    assert store.list_notifications("user-1", status=InAppStatus.UNREAD) == []


def test_in_app_store_pin_and_unpin() -> None:
    store = InAppNotificationStore()
    message = build_notification(
        channel=NotificationChannel.IN_APP,
        notification_type=NotificationType.INFORMATION,
        body="Welcome",
        user_id="user-1",
    )
    store.add(message)

    store.set_pinned("user-1", message.notification_id, pinned=True)
    assert store.list_notifications("user-1")[0].pinned is True

    store.set_pinned("user-1", message.notification_id, pinned=False)
    assert store.list_notifications("user-1")[0].pinned is False


def test_in_app_store_unread_count() -> None:
    store = InAppNotificationStore()
    for _ in range(3):
        store.add(
            build_notification(
                channel=NotificationChannel.IN_APP,
                notification_type=NotificationType.INFORMATION,
                body="x",
                user_id="user-1",
            )
        )

    assert store.unread_count("user-1") == 3


def test_in_app_store_list_filters_by_category() -> None:
    store = InAppNotificationStore()
    store.add(
        build_notification(
            channel=NotificationChannel.IN_APP,
            notification_type=NotificationType.INFORMATION,
            body="a",
            user_id="user-1",
        ),
        category="billing",
    )
    store.add(
        build_notification(
            channel=NotificationChannel.IN_APP,
            notification_type=NotificationType.INFORMATION,
            body="b",
            user_id="user-1",
        ),
        category="security",
    )

    billing_only = store.list_notifications("user-1", category="billing")

    assert len(billing_only) == 1
    assert billing_only[0].category == "billing"


def test_in_app_store_list_paginates_newest_first() -> None:
    store = InAppNotificationStore()
    for i in range(5):
        store.add(
            build_notification(
                channel=NotificationChannel.IN_APP,
                notification_type=NotificationType.INFORMATION,
                body=f"msg-{i}",
                user_id="user-1",
            )
        )

    page_one = store.list_notifications("user-1", page=1, page_size=2)
    page_two = store.list_notifications("user-1", page=2, page_size=2)

    assert [r.message.body for r in page_one] == ["msg-4", "msg-3"]
    assert [r.message.body for r in page_two] == ["msg-2", "msg-1"]


def test_in_app_store_search_matches_body_title_and_subject() -> None:
    store = InAppNotificationStore()
    store.add(
        build_notification(
            channel=NotificationChannel.IN_APP,
            notification_type=NotificationType.INFORMATION,
            body="Your invoice is ready",
            user_id="user-1",
        )
    )
    store.add(
        build_notification(
            channel=NotificationChannel.IN_APP,
            notification_type=NotificationType.INFORMATION,
            body="unrelated",
            user_id="user-1",
        )
    )

    results = store.search("user-1", "invoice")

    assert len(results) == 1
    assert "invoice" in results[0].message.body


async def test_in_app_channel_delivers_into_the_store() -> None:
    store = InAppNotificationStore()
    channel = InAppChannel(store)
    message = build_notification(
        channel=NotificationChannel.IN_APP,
        notification_type=NotificationType.INFORMATION,
        body="Welcome",
        user_id="user-1",
    )

    result = await channel.send(message)

    assert result.status == DeliveryStatus.DELIVERED
    assert len(store.list_notifications("user-1")) == 1
