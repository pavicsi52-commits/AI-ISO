"""Discord channel.

Per docs/025_Enterprise_Notification_Framework.md.txt "CHANNELS":
Discord. Delivers via a Discord incoming webhook.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.notifications.channels import NotificationMessage, WebhookUrlResolver
from shared_core.notifications.constants import DEFAULT_DELIVERY_TIMEOUT_SECONDS
from shared_core.notifications.delivery import DeliveryResult, DeliveryStatus, build_delivery_result

_DISCORD_MESSAGE_MAX_LENGTH = 2000


class DiscordChannel:
    """Sends notifications to a Discord incoming webhook."""

    channel_type = NotificationChannel.DISCORD

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
        payload = build_discord_payload(message)
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


def build_discord_payload(message: NotificationMessage) -> dict[str, Any]:
    """Build a Discord incoming-webhook payload for *message*.

    Discord truncates (server-side, with an error, not silently) any
    ``content`` over 2000 characters -- truncated here first so a long
    notification degrades to a shortened message instead of failing
    delivery outright.
    """
    text = f"**{message.title}**\n{message.body}" if message.title else message.body
    if len(text) > _DISCORD_MESSAGE_MAX_LENGTH:
        text = text[: _DISCORD_MESSAGE_MAX_LENGTH - 1] + "…"
    return {"content": text}


__all__ = ["DiscordChannel", "build_discord_payload"]
