"""SMS channel.

Per docs/025_Enterprise_Notification_Framework.md.txt "CHANNELS": SMS
Provider. Docs/025 names no specific vendor (Twilio, Vonage,
MessageBird, ...), and every one of them speaks a different REST API --
so this is a generic HTTP POST provider, configured with the endpoint
and auth a real vendor integration supplies; a service wiring in a
specific provider passes that provider's send-SMS URL and headers here
rather than this framework special-casing one vendor's API shape.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.notifications.channels import NotificationMessage
from shared_core.notifications.constants import DEFAULT_DELIVERY_TIMEOUT_SECONDS
from shared_core.notifications.delivery import DeliveryResult, DeliveryStatus, build_delivery_result

PhoneNumberResolver = Callable[[NotificationMessage], str]


class SmsChannel:
    """Sends notifications via a generic HTTP SMS provider."""

    channel_type = NotificationChannel.SMS

    def __init__(
        self,
        *,
        endpoint: str,
        phone_number_resolver: PhoneNumberResolver,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = DEFAULT_DELIVERY_TIMEOUT_SECONDS,
    ):
        self._endpoint = endpoint
        self._phone_number_resolver = phone_number_resolver
        self._headers = dict(headers) if headers else {}
        self._timeout_seconds = timeout_seconds

    async def send(self, message: NotificationMessage) -> DeliveryResult:
        to_number = self._phone_number_resolver(message)
        payload = build_sms_payload(message, to_number=to_number)
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(self._endpoint, json=payload, headers=self._headers)
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


def build_sms_payload(message: NotificationMessage, *, to_number: str) -> dict[str, Any]:
    """Build a generic SMS provider payload for *message*."""
    return {"to": to_number, "body": message.body}


__all__ = ["PhoneNumberResolver", "SmsChannel", "build_sms_payload"]
