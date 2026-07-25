"""SMTP Email channel.

Per docs/025_Enterprise_Notification_Framework.md.txt "CHANNELS":
SMTP Email. Sends a multipart ``plain + html`` message when
``message.metadata["body_format"]`` is ``"html"`` or ``"markdown"``
(matching :class:`~shared_core.notifications.templates.TemplateFormat`'s
values -- the convention a caller who rendered the body via
:func:`shared_core.notifications.renderer.render_template` sets); plain
text otherwise. ``metadata`` is the message model's own documented
extension point (docs/025 "MESSAGE MODEL"), so this doesn't need a
dedicated field on :class:`~shared_core.notifications.channels
.NotificationMessage` itself.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from email.message import EmailMessage

import aiosmtplib

from shared_core.config.settings import EmailSettings
from shared_core.enums.notification_channel import NotificationChannel
from shared_core.notifications.channels import NotificationMessage
from shared_core.notifications.delivery import DeliveryResult, DeliveryStatus, build_delivery_result
from shared_core.notifications.renderer import RenderedNotification, render_to_html
from shared_core.notifications.templates import TemplateFormat

ToAddressResolver = Callable[[NotificationMessage], str]

_HTML_BODY_FORMATS = frozenset({TemplateFormat.HTML.value, TemplateFormat.MARKDOWN.value})


class EmailChannel:
    """Sends notifications over SMTP using :mod:`aiosmtplib`."""

    channel_type = NotificationChannel.EMAIL

    def __init__(self, settings: EmailSettings, *, to_address_resolver: ToAddressResolver):
        self._settings = settings
        self._to_address_resolver = to_address_resolver

    async def send(self, message: NotificationMessage) -> DeliveryResult:
        to_address = self._to_address_resolver(message)
        start = time.perf_counter()
        email_message = _build_email_message(
            message, from_address=self._settings.email_from_address, to_address=to_address
        )
        try:
            await aiosmtplib.send(
                email_message,
                hostname=self._settings.smtp_host,
                port=self._settings.smtp_port,
                username=self._settings.smtp_user or None,
                password=self._settings.smtp_password or None,
                use_tls=self._settings.smtp_use_tls,
            )
        except (aiosmtplib.SMTPException, OSError, TimeoutError) as exc:
            return build_delivery_result(
                status=DeliveryStatus.FAILED, channel=self.channel_type, error=str(exc)
            )
        latency_ms = (time.perf_counter() - start) * 1000
        return build_delivery_result(
            status=DeliveryStatus.SENT, channel=self.channel_type, latency_ms=latency_ms
        )


def render_email_body(rendered: RenderedNotification) -> tuple[str, str]:
    """Return ``(plain_text, html)`` bodies for *rendered*, for a multipart email."""
    html = render_to_html(rendered)
    plain = rendered.body
    return plain, html


def _build_email_message(
    message: NotificationMessage, *, from_address: str, to_address: str
) -> EmailMessage:
    email_message = EmailMessage()
    email_message["From"] = from_address
    email_message["To"] = to_address
    email_message["Subject"] = message.subject or message.title or "Notification"

    body_format = message.metadata.get("body_format")
    if body_format in _HTML_BODY_FORMATS:
        rendered = RenderedNotification(body=message.body, format=TemplateFormat(body_format))
        plain, html = render_email_body(rendered)
        email_message.set_content(plain)
        email_message.add_alternative(html, subtype="html")
    else:
        email_message.set_content(message.body)

    for attachment in message.attachments:
        maintype, _slash, subtype = attachment.content_type.partition("/")
        email_message.add_attachment(
            attachment.data,
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=attachment.filename,
        )
    return email_message


__all__ = ["EmailChannel", "ToAddressResolver", "render_email_body"]
