"""Tests for slack.py, teams.py, discord.py, and webhook.py against a real HTTP server."""

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
from shared_core.notifications.discord import DiscordChannel, build_discord_payload
from shared_core.notifications.exceptions import WebhookSignatureError
from shared_core.notifications.slack import SlackChannel, build_slack_payload
from shared_core.notifications.teams import TeamsChannel, build_teams_payload
from shared_core.notifications.webhook import (
    WebhookChannel,
    build_webhook_payload,
    sign_payload,
    verify_signature,
)


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
def webhook_server() -> Iterator[str]:
    _CapturingHandler.received = []
    _CapturingHandler.received_headers = []
    _CapturingHandler.response_status = 200
    server = HTTPServer(("localhost", 0), _CapturingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://localhost:{server.server_port}/hook"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def _message(channel: NotificationChannel):  # type: ignore[no-untyped-def]
    return build_notification(
        channel=channel,
        notification_type=NotificationType.CRITICAL,
        body="Disk usage at 95%.",
        title="Disk Alert",
    )


# --- slack.py ---


def test_build_slack_payload_includes_title_and_body() -> None:
    payload = build_slack_payload(_message(NotificationChannel.SLACK))

    assert "Disk Alert" in payload["text"]
    assert "Disk usage at 95%." in payload["text"]


async def test_slack_channel_posts_to_the_webhook(webhook_server: str) -> None:
    channel = SlackChannel(webhook_url_resolver=lambda _m: webhook_server)

    result = await channel.send(_message(NotificationChannel.SLACK))

    assert result.status == DeliveryStatus.SENT
    assert len(_CapturingHandler.received) == 1
    assert "Disk Alert" in _CapturingHandler.received[0]["text"]


async def test_slack_channel_reports_failure_on_a_non_2xx_response(webhook_server: str) -> None:
    _CapturingHandler.response_status = 500
    channel = SlackChannel(webhook_url_resolver=lambda _m: webhook_server)

    result = await channel.send(_message(NotificationChannel.SLACK))

    assert result.status == DeliveryStatus.FAILED
    assert result.error is not None


async def test_slack_channel_reports_failure_when_unreachable() -> None:
    channel = SlackChannel(webhook_url_resolver=lambda _m: "http://localhost:1/hook")

    result = await channel.send(_message(NotificationChannel.SLACK))

    assert result.status == DeliveryStatus.FAILED


# --- teams.py ---


def test_build_teams_payload_is_a_message_card() -> None:
    payload = build_teams_payload(_message(NotificationChannel.TEAMS))

    assert payload["@type"] == "MessageCard"
    assert payload["title"] == "Disk Alert"
    assert payload["themeColor"] == "B71C1C"  # notification_type == CRITICAL


async def test_teams_channel_posts_to_the_webhook(webhook_server: str) -> None:
    channel = TeamsChannel(webhook_url_resolver=lambda _m: webhook_server)

    result = await channel.send(_message(NotificationChannel.TEAMS))

    assert result.status == DeliveryStatus.SENT
    assert _CapturingHandler.received[0]["@type"] == "MessageCard"


async def test_teams_channel_reports_failure_when_unreachable() -> None:
    channel = TeamsChannel(webhook_url_resolver=lambda _m: "http://localhost:1/hook")

    result = await channel.send(_message(NotificationChannel.TEAMS))

    assert result.status == DeliveryStatus.FAILED
    assert result.error is not None


# --- discord.py ---


def test_build_discord_payload_truncates_long_content() -> None:
    message = _message(NotificationChannel.DISCORD)
    message.body = "x" * 3000

    payload = build_discord_payload(message)

    assert len(payload["content"]) == 2000
    assert payload["content"].endswith("…")


async def test_discord_channel_posts_to_the_webhook(webhook_server: str) -> None:
    channel = DiscordChannel(webhook_url_resolver=lambda _m: webhook_server)

    result = await channel.send(_message(NotificationChannel.DISCORD))

    assert result.status == DeliveryStatus.SENT
    assert "content" in _CapturingHandler.received[0]


async def test_discord_channel_reports_failure_when_unreachable() -> None:
    channel = DiscordChannel(webhook_url_resolver=lambda _m: "http://localhost:1/hook")

    result = await channel.send(_message(NotificationChannel.DISCORD))

    assert result.status == DeliveryStatus.FAILED
    assert result.error is not None


# --- webhook.py ---


def test_build_webhook_payload_includes_every_core_field() -> None:
    payload = build_webhook_payload(_message(NotificationChannel.WEBHOOK))

    assert payload["notification_type"] == "critical"
    assert payload["title"] == "Disk Alert"


def test_sign_and_verify_signature_roundtrips() -> None:
    body = b'{"a": 1}'
    signature = sign_payload(body, secret="s3cr3t")

    verify_signature(body, signature, secret="s3cr3t")


def test_verify_signature_rejects_a_tampered_body() -> None:
    body = b'{"a": 1}'
    signature = sign_payload(body, secret="s3cr3t")

    with pytest.raises(WebhookSignatureError):
        verify_signature(b'{"a": 2}', signature, secret="s3cr3t")


async def test_webhook_channel_posts_the_default_payload(webhook_server: str) -> None:
    channel = WebhookChannel(webhook_url_resolver=lambda _m: webhook_server)

    result = await channel.send(_message(NotificationChannel.WEBHOOK))

    assert result.status == DeliveryStatus.SENT
    assert _CapturingHandler.received[0]["title"] == "Disk Alert"


async def test_webhook_channel_reports_failure_on_a_non_2xx_response(webhook_server: str) -> None:
    _CapturingHandler.response_status = 500
    channel = WebhookChannel(webhook_url_resolver=lambda _m: webhook_server)

    result = await channel.send(_message(NotificationChannel.WEBHOOK))

    assert result.status == DeliveryStatus.FAILED
    assert result.error is not None


async def test_webhook_channel_reports_failure_when_unreachable() -> None:
    channel = WebhookChannel(webhook_url_resolver=lambda _m: "http://localhost:1/hook")

    result = await channel.send(_message(NotificationChannel.WEBHOOK))

    assert result.status == DeliveryStatus.FAILED
    assert result.error is not None


async def test_webhook_channel_signs_the_payload_when_configured(webhook_server: str) -> None:
    channel = WebhookChannel(
        webhook_url_resolver=lambda _m: webhook_server, signing_secret="s3cr3t"
    )

    await channel.send(_message(NotificationChannel.WEBHOOK))

    headers = _CapturingHandler.received_headers[0]
    assert "X-AIIOS-Signature" in headers


async def test_webhook_channel_sends_custom_headers(webhook_server: str) -> None:
    channel = WebhookChannel(
        webhook_url_resolver=lambda _m: webhook_server, headers={"X-Custom": "abc"}
    )

    await channel.send(_message(NotificationChannel.WEBHOOK))

    assert _CapturingHandler.received_headers[0]["X-Custom"] == "abc"


async def test_webhook_channel_uses_a_custom_payload_builder(webhook_server: str) -> None:
    channel = WebhookChannel(
        webhook_url_resolver=lambda _m: webhook_server,
        payload_builder=lambda message: {"custom": message.body},
    )

    await channel.send(_message(NotificationChannel.WEBHOOK))

    assert _CapturingHandler.received[0] == {"custom": "Disk usage at 95%."}
