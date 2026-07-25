"""Notification dispatch.

Per docs/025_Enterprise_Notification_Framework.md.txt "RETRY"/
"DELIVERY": the orchestration layer that actually sends one
notification -- rate limiting, retry-with-backoff, history recording,
and dead-lettering on exhaustion. :mod:`shared_core.notifications.router`
decides *which* channel(s) and *when*; this module does the sending
once that's decided.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from shared_core.notifications.channels import ChannelRegistry, NotificationMessage
from shared_core.notifications.delivery import DeliveryResult, DeliveryStatus, build_delivery_result
from shared_core.notifications.history import HistoryStore
from shared_core.notifications.ratelimit import NotificationRateLimiter
from shared_core.notifications.retry import (
    DeadLetterStore,
    RetryPolicy,
    classify_delivery_failure,
    notification_retry_policy,
)


class NotificationDispatcher:
    """Sends one notification through its channel, with retry, history, and dead-lettering."""

    def __init__(
        self,
        *,
        channels: ChannelRegistry,
        history: HistoryStore,
        dead_letters: DeadLetterStore,
        retry_policy: RetryPolicy | None = None,
        rate_limiter: NotificationRateLimiter | None = None,
    ):
        self._channels = channels
        self._history = history
        self._dead_letters = dead_letters
        self._retry_policy = retry_policy or notification_retry_policy()
        self._rate_limiter = rate_limiter

    async def dispatch(self, message: NotificationMessage) -> DeliveryResult:
        """Send *message*, retrying transient failures up to the configured policy.

        Records every attempt to ``history``; dead-letters (see
        :mod:`shared_core.notifications.retry`) if every attempt fails.
        Updates *message*'s own ``status``/``sent_at``/``delivered_at``
        in place to reflect the final outcome.
        """
        if self._rate_limiter is not None:
            rate_status = await self._rate_limiter.check(
                user_id=message.user_id,
                organization_id=message.organization_id,
                channel=message.channel,
            )
            if not rate_status.allowed:
                result = build_delivery_result(
                    status=DeliveryStatus.FAILED,
                    channel=message.channel,
                    error="Rate limit exceeded.",
                )
                message.status = result.status
                self._history.record(message.notification_id, attempt=1, result=result)
                return result

        channel = self._channels.get(message.channel)
        retry_count = 0
        while True:
            result = await channel.send(message)
            self._history.record(message.notification_id, attempt=retry_count + 1, result=result)
            if result.status != DeliveryStatus.FAILED:
                break
            if (
                not classify_delivery_failure(result)
                or retry_count >= self._retry_policy.max_attempts
            ):
                break
            await asyncio.sleep(self._retry_policy.delay_for(retry_count + 1))
            retry_count += 1

        message.status = result.status
        now = datetime.now(UTC)
        if result.status in (DeliveryStatus.SENT, DeliveryStatus.DELIVERED):
            message.sent_at = now
        if result.status == DeliveryStatus.DELIVERED:
            message.delivered_at = now
        if result.status == DeliveryStatus.FAILED:
            self._dead_letters.add(message, last_result=result, attempts=retry_count + 1)
        return result


__all__ = ["NotificationDispatcher"]
