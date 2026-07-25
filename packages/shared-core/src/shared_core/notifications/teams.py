"""Microsoft Teams channel.

Per docs/025_Enterprise_Notification_Framework.md.txt "CHANNELS":
Microsoft Teams. Delivers via a Teams incoming webhook using the
``MessageCard`` payload format.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.notifications.channels import NotificationMessage, WebhookUrlResolver
from shared_core.notifications.constants import DEFAULT_DELIVERY_TIMEOUT_SECONDS
from shared_core.notifications.delivery import DeliveryResult, DeliveryStatus, build_delivery_result

_THEME_COLOR_BY_TYPE_PREFIX: dict[str, str] = {
    "error": "D32F2F",
    "critical": "B71C1C",
    "warning": "F9A825",
    "success": "2E7D32",
}
_DEFAULT_THEME_COLOR = "0078D4"


class TeamsChannel:
    """Sends notifications to a Microsoft Teams incoming webhook."""

    channel_type = NotificationChannel.TEAMS

    def __init__(
        self,
        *,
        webhook_url_resolver: WebhookUrlResolver,
        timeout_seconds: float = DEFAULT_DELIVERY_TIMEOUT_SECONDS,
    ):
        self._webhook_url_resolver = webhook_url_resolver
        self._timeout_seconds = timeout_seconds

    async def send(self, message: NotificationMessage) -> DeliveryResult:
        url = self._webhook_url_resolver(message)
        payload = build_teams_payload(message)
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(url, json=payload)
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


def build_teams_payload(message: NotificationMessage) -> dict[str, Any]:
    """Build a Teams incoming-webhook ``MessageCard`` payload for *message*."""
    theme_color = _THEME_COLOR_BY_TYPE_PREFIX.get(
        message.notification_type.value, _DEFAULT_THEME_COLOR
    )
    return {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": message.subject or message.title or "Notification",
        "themeColor": theme_color,
        "title": message.title or message.subject or "",
        "text": message.body,
    }


__all__ = ["TeamsChannel", "build_teams_payload"]
