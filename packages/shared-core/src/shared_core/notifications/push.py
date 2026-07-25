"""Push notification channel.

Per docs/025_Enterprise_Notification_Framework.md.txt "CHANNELS": Push
Provider. Docs/025 names no specific vendor (FCM, APNs, ...) -- like
:mod:`shared_core.notifications.sms`, this is a generic HTTP POST
provider a real vendor integration configures.
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

DeviceTokenResolver = Callable[[NotificationMessage], str]


class PushChannel:
    """Sends notifications via a generic HTTP push provider."""

    channel_type = NotificationChannel.PUSH

    def __init__(
        self,
        *,
        endpoint: str,
        device_token_resolver: DeviceTokenResolver,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = DEFAULT_DELIVERY_TIMEOUT_SECONDS,
    ):
        self._endpoint = endpoint
        self._device_token_resolver = device_token_resolver
        self._headers = dict(headers) if headers else {}
        self._timeout_seconds = timeout_seconds

    async def send(self, message: NotificationMessage) -> DeliveryResult:
        device_token = self._device_token_resolver(message)
        payload = build_push_payload(message, device_token=device_token)
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


def build_push_payload(message: NotificationMessage, *, device_token: str) -> dict[str, Any]:
    """Build a generic push provider payload for *message*."""
    return {
        "to": device_token,
        "title": message.title or message.subject or "",
        "body": message.body,
        "data": message.metadata,
    }


__all__ = ["DeviceTokenResolver", "PushChannel", "build_push_payload"]
