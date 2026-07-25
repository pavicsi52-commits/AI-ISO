"""Message producer.

Per docs/021_Enterprise_Queue_Framework.md.txt "PRODUCER": Publish, Batch
Publish, Scheduled Publish, Priority Publish, Async Publish,
Confirmation, Timeout, Retry.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from shared_core.enums.priority import Priority
from shared_core.queue.delay import declare_delay_queue, delay_until
from shared_core.queue.exceptions import PublishFailedError
from shared_core.queue.manager import QueueManager
from shared_core.queue.priority import priority_level
from shared_core.queue.retry import RetryPolicy
from shared_core.queue.serializer import SerializationFormat
from shared_core.types.queue import QueueMessage


class Producer:
    """Ergonomic publish facade over :class:`~shared_core.queue.manager.QueueManager`.

    :meth:`QueueManager.publish` already provides "Confirmation" (it
    doesn't return until the broker accepts the message) and per-message
    "Priority Publish" (a ``priority`` kwarg); this adds retry-with-
    backoff ("Retry"), a publish deadline ("Timeout"), batching, async
    scheduling, and time-delayed publish on top.
    """

    def __init__(
        self, queue_manager: QueueManager, *, retry_policy: RetryPolicy | None = None
    ) -> None:
        self._queue_manager = queue_manager
        self._retry_policy = retry_policy or RetryPolicy()

    async def publish(
        self,
        queue_name: str,
        message: QueueMessage,
        *,
        priority: Priority | None = None,
        format: SerializationFormat = SerializationFormat.JSON,
        timeout_seconds: float | None = None,
    ) -> None:
        """Publish a message, retrying transient failures with backoff.

        Raises:
            PublishFailedError: If every retry attempt is exhausted, or
                *timeout_seconds* elapses first.
        """
        coro = self._publish_with_retry(queue_name, message, priority, format)
        if timeout_seconds is None:
            await coro
            return
        try:
            await asyncio.wait_for(coro, timeout=timeout_seconds)
        except TimeoutError as exc:
            raise PublishFailedError(
                f"Publishing to '{queue_name}' timed out after {timeout_seconds}s."
            ) from exc

    async def _publish_with_retry(
        self,
        queue_name: str,
        message: QueueMessage,
        priority: Priority | None,
        format: SerializationFormat,
    ) -> None:
        priority_value = priority_level(priority) if priority is not None else None
        last_error: Exception | None = None
        for attempt in range(1, self._retry_policy.max_attempts + 1):
            try:
                await self._queue_manager.publish(
                    queue_name, message, priority=priority_value, format=format
                )
                return
            except Exception as exc:
                last_error = exc
                is_final_attempt = attempt == self._retry_policy.max_attempts
                if not self._retry_policy.classify(exc) or is_final_attempt:
                    break
                await asyncio.sleep(self._retry_policy.delay_for(attempt))
        raise PublishFailedError(
            f"Failed to publish to '{queue_name}' after "
            f"{self._retry_policy.max_attempts} attempt(s)."
        ) from last_error

    async def publish_batch(
        self, queue_name: str, messages: Iterable[QueueMessage], **kwargs: Any
    ) -> None:
        """Publish every message in *messages*, in order ("Batch Publish").

        Raises:
            PublishFailedError: On the first message that fails all its
                retry attempts; earlier messages in the batch have
                already been published and are not rolled back.
        """
        for message in messages:
            await self.publish(queue_name, message, **kwargs)

    def publish_async(
        self, queue_name: str, message: QueueMessage, **kwargs: Any
    ) -> asyncio.Task[None]:
        """Schedule a publish without waiting for it ("Async Publish").

        Returns the created task so callers who do want to observe
        completion/errors may ``await`` it themselves.
        """
        return asyncio.create_task(self.publish(queue_name, message, **kwargs))

    async def publish_scheduled(
        self,
        queue_name: str,
        message: QueueMessage,
        *,
        at: datetime,
        format: SerializationFormat = SerializationFormat.JSON,
    ) -> None:
        """Publish a message that becomes available at a specific future time ("Scheduled Publish").

        Raises:
            InvalidDelayError: If *at* is in the past, or too far in the future.
        """
        delay_ms = delay_until(at)
        channel = await self._queue_manager.channel()
        holding_name = await declare_delay_queue(channel, queue_name, delay_ms)
        await self._queue_manager.publish(holding_name, message, format=format)


__all__ = ["Producer"]
