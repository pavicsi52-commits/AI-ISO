"""Generic REST webhook channel.

Per docs/025_Enterprise_Notification_Framework.md.txt "WEBHOOKS": REST,
Authentication, Retry, Signature Verification, Custom Headers, Payload
Templates. (Retry is this channel's caller's concern --
:mod:`shared_core.notifications.retry` -- not reimplemented here.)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Callable
from typing import Any

import httpx

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.notifications.channels import NotificationMessage, WebhookUrlResolver
from shared_core.notifications.constants import (
    DEFAULT_DELIVERY_TIMEOUT_SECONDS,
    DEFAULT_WEBHOOK_SIGNATURE_HEADER,
)
from shared_core.notifications.delivery import DeliveryResult, DeliveryStatus, build_delivery_result
from shared_core.notifications.exceptions import WebhookSignatureError

PayloadBuilder = Callable[[NotificationMessage], dict[str, Any]]


def build_webhook_payload(message: NotificationMessage) -> dict[str, Any]:
    """Build the default JSON payload for *message* ("REST")."""
    return {
        "notification_id": message.notification_id,
        "notification_type": message.notification_type.value,
        "priority": message.priority.value,
        "organization_id": message.organization_id,
        "project_id": message.project_id,
        "user_id": message.user_id,
        "subject": message.subject,
        "title": message.title,
        "body": message.body,
        "metadata": message.metadata,
    }


def sign_payload(body: bytes, *, secret: str) -> str:
    """HMAC-SHA256 sign *body*, hex-encoded ("Signature Verification")."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_signature(body: bytes, signature: str, *, secret: str) -> None:
    """Verify *signature* against *body*.

    Raises:
        WebhookSignatureError: If the signature doesn't match.
    """
    expected = sign_payload(body, secret=secret)
    if not hmac.compare_digest(expected, signature):
        raise WebhookSignatureError("Webhook signature verification failed.")


class WebhookChannel:
    """Sends notifications to a generic REST webhook endpoint."""

    channel_type = NotificationChannel.WEBHOOK

    def __init__(
        self,
        *,
        webhook_url_resolver: WebhookUrlResolver,
        signing_secret: str | None = None,
        headers: dict[str, str] | None = None,
        payload_builder: PayloadBuilder | None = None,
        timeout_seconds: float = DEFAULT_DELIVERY_TIMEOUT_SECONDS,
    ):
        self._webhook_url_resolver = webhook_url_resolver
        self._signing_secret = signing_secret
        self._headers = dict(headers) if headers else {}
        self._payload_builder = payload_builder or build_webhook_payload
        self._timeout_seconds = timeout_seconds

    async def send(self, message: NotificationMessage) -> DeliveryResult:
        url = self._webhook_url_resolver(message)
        body = json.dumps(self._payload_builder(message)).encode("utf-8")
        headers = {"Content-Type": "application/json", **self._headers}
        if self._signing_secret is not None:
            headers[DEFAULT_WEBHOOK_SIGNATURE_HEADER] = sign_payload(
                body, secret=self._signing_secret
            )
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(url, content=body, headers=headers)
        except httpx.HTTPError as exc:
            return build_delivery_result(
                status=DeliveryStatus.FAILED, channel=self.channel_type, error=str(exc)
            )
        latency_ms = (time.perf_counter() - start) * 1000
        if not response.is_success:
            return build_delivery_result(
                status=DeliveryStatus.FAILED,
                channel=self.channel_type,
                error=f"HTTP {response.status_code}: {response.text}",
                latency_ms=latency_ms,
            )
        return build_delivery_result(
            status=DeliveryStatus.SENT, channel=self.channel_type, latency_ms=latency_ms
        )


__all__ = [
    "PayloadBuilder",
    "WebhookChannel",
    "build_webhook_payload",
    "sign_payload",
    "verify_signature",
]
