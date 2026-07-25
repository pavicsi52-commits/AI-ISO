"""Tests for email.py, against a real (throwaway, in-process) SMTP server."""

from __future__ import annotations

import socket
from collections.abc import Iterator
from email.message import Message as EmailLibMessage

import pytest
from aiosmtpd.controller import Controller
from aiosmtpd.handlers import Message as SmtpdMessageHandler
from shared_core.config.settings import EmailSettings
from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.enums.priority import Priority
from shared_core.notifications.attachments import Attachment, AttachmentKind
from shared_core.notifications.channels import build_notification
from shared_core.notifications.delivery import DeliveryStatus
from shared_core.notifications.email import EmailChannel


class _CapturingHandler(SmtpdMessageHandler):
    def __init__(self) -> None:
        super().__init__()
        self.received: list[EmailLibMessage] = []

    def handle_message(self, message: EmailLibMessage) -> None:
        self.received.append(message)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("localhost", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def smtp_server() -> Iterator[tuple[Controller, _CapturingHandler, int]]:
    handler = _CapturingHandler()
    port = _free_port()
    controller = Controller(handler, hostname="localhost", port=port)
    controller.start()
    try:
        yield controller, handler, port
    finally:
        controller.stop()


def _email_settings(port: int) -> EmailSettings:
    return EmailSettings(
        email_enabled=True,
        smtp_host="localhost",
        smtp_port=port,
        smtp_user="",
        smtp_password="",
        smtp_use_tls=False,
        email_from_address="noreply@aiios.local",
        _env_file=None,
    )


async def test_email_channel_sends_a_real_message_over_smtp(
    smtp_server: tuple[Controller, _CapturingHandler, int],
) -> None:
    _controller, handler, port = smtp_server
    channel = EmailChannel(
        _email_settings(port), to_address_resolver=lambda _message: "user@example.com"
    )
    message = build_notification(
        channel=NotificationChannel.EMAIL,
        notification_type=NotificationType.INFORMATION,
        body="Your report is ready.",
        subject="Report Ready",
        priority=Priority.NORMAL,
    )

    result = await channel.send(message)

    assert result.status == DeliveryStatus.SENT
    assert result.latency_ms is not None
    assert len(handler.received) == 1
    received = handler.received[0]
    assert received["Subject"] == "Report Ready"
    assert received["To"] == "user@example.com"


async def test_email_channel_delivers_attachments(
    smtp_server: tuple[Controller, _CapturingHandler, int],
) -> None:
    _controller, handler, port = smtp_server
    channel = EmailChannel(
        _email_settings(port), to_address_resolver=lambda _message: "user@example.com"
    )
    message = build_notification(
        channel=NotificationChannel.EMAIL,
        notification_type=NotificationType.INFORMATION,
        body="See attached.",
        subject="Report",
        attachments=[
            Attachment(
                filename="report.csv",
                content_type="text/csv",
                kind=AttachmentKind.CSV,
                data=b"a,b,c\n1,2,3\n",
            )
        ],
    )

    result = await channel.send(message)

    assert result.status == DeliveryStatus.SENT
    received = handler.received[0]
    filenames = [part.get_filename() for part in received.walk() if part.get_filename()]
    assert "report.csv" in filenames


async def test_email_channel_sends_a_multipart_html_message_when_requested(
    smtp_server: tuple[Controller, _CapturingHandler, int],
) -> None:
    _controller, handler, port = smtp_server
    channel = EmailChannel(
        _email_settings(port), to_address_resolver=lambda _message: "user@example.com"
    )
    message = build_notification(
        channel=NotificationChannel.EMAIL,
        notification_type=NotificationType.INFORMATION,
        body="# Report Ready\n\nSee the attached data.",
        subject="Report Ready",
        metadata={"body_format": "markdown"},
    )

    result = await channel.send(message)

    assert result.status == DeliveryStatus.SENT
    received = handler.received[0]
    assert received.is_multipart()
    html_parts = [
        part.get_payload(decode=True)
        for part in received.walk()
        if part.get_content_type() == "text/html"
    ]
    assert html_parts
    assert b"<h1>Report Ready</h1>" in html_parts[0]


async def test_email_channel_reports_failure_when_smtp_is_unreachable() -> None:
    channel = EmailChannel(
        _email_settings(1), to_address_resolver=lambda _message: "user@example.com"
    )
    message = build_notification(
        channel=NotificationChannel.EMAIL, notification_type=NotificationType.ERROR, body="oops"
    )

    result = await channel.send(message)

    assert result.status == DeliveryStatus.FAILED
    assert result.error is not None
