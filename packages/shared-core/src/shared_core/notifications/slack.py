"""Slack channel.

Per docs/025_Enterprise_Notification_Framework.md.txt "CHANNELS": Slack.
Delivers via a Slack incoming webhook -- the standard integration point
for posting into a channel without a full Slack App/bot token.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.notifications.channels import NotificationMessage, WebhookUrlResolver
from shared_core.notifications.constants import DEFAULT_DELIVERY_TIMEOUT_SECONDS
from shared_core.notifications.delivery import DeliveryResult, DeliveryStatus, build_delivery_result


class SlackChannel:
    """Sends notifications to a Slack incoming webhook."""

    channel_type = NotificationChannel.SLACK

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
        payload = build_slack_payload(message)
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


def build_slack_payload(message: NotificationMessage) -> dict[str, Any]:
    """Build a Slack incoming-webhook payload for *message*."""
    text = f"*{message.title}*\n{message.body}" if message.title else message.body
    return {"text": text}


__all__ = ["SlackChannel", "build_slack_payload"]
