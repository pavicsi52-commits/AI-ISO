"""RabbitMQ queue manager.

The only place any AI-IOS service talks to RabbitMQ directly, per
docs/012_Shared_Core_Framework.md.txt "QUEUE". Every queue is declared with
a dead-letter exchange so poison messages never loop forever. Retry
backoff (docs/021_Enterprise_Queue_Framework.md.txt "RETRY POLICY") is
implemented by requeuing a failed message through a
:mod:`shared_core.queue.delay`-backed holding queue rather than
republishing it immediately, so a retrying consumer doesn't hot-loop.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage, AbstractRobustConnection

from shared_core.constants.rabbitmq import RabbitMQConstants
from shared_core.queue.delay import declare_delay_queue
from shared_core.queue.metrics import (
    measure_processing,
    record_consumed,
    record_dead_lettered,
    record_failed,
    record_published,
    record_retried,
)
from shared_core.queue.retry import RetryPolicy, compute_backoff_delay_ms
from shared_core.queue.serializer import SerializationFormat, deserialize_message, serialize_message
from shared_core.queue.statistics import QueueStatistics
from shared_core.types.queue import QueueMessage

RETRY_COUNT_HEADER = "x-retry-count"

_CONTENT_TYPE_BY_FORMAT: dict[SerializationFormat, str] = {
    SerializationFormat.JSON: "application/json",
    SerializationFormat.MSGPACK: "application/msgpack",
}
_FORMAT_BY_CONTENT_TYPE: dict[str, SerializationFormat] = {
    content_type: format_ for format_, content_type in _CONTENT_TYPE_BY_FORMAT.items()
}


class QueueManager:
    """Serializing wrapper around an aio-pika connection.

    Carries its own :class:`~shared_core.queue.statistics.QueueStatistics`
    (in-process rolling counters, e.g. for
    :func:`shared_core.queue.health.check_queue_health`) alongside the
    Prometheus counters :mod:`shared_core.queue.metrics` records on every
    publish/consume/retry/dead-letter -- the two serve different
    consumers (a single process's own health check vs. a
    scrape-and-aggregate monitoring stack) and are updated together.
    """

    def __init__(self, connection: AbstractRobustConnection) -> None:
        self._connection = connection
        self._channel: AbstractChannel | None = None
        self.statistics = QueueStatistics()

    async def channel(self) -> AbstractChannel:
        """Return the shared channel, opening it on first use."""
        if self._channel is None or self._channel.is_closed:
            self._channel = await self._connection.channel()
            await self._channel.set_qos(prefetch_count=RabbitMQConstants.DEFAULT_PREFETCH_COUNT)
        return self._channel

    async def declare_queue_with_dlq(self, queue_name: str) -> tuple[str, str]:
        """Declare ``queue_name`` with a matching dead-letter queue.

        Returns:
            The ``(queue_name, dead_letter_queue_name)`` pair.
        """
        channel = await self.channel()
        dlx_name = f"{queue_name}.dlx"
        dlq_name = f"{queue_name}.dlq"

        dlx = await channel.declare_exchange(dlx_name, aio_pika.ExchangeType.FANOUT, durable=True)
        dead_letter_queue = await channel.declare_queue(dlq_name, durable=True)
        await dead_letter_queue.bind(dlx)

        await channel.declare_queue(
            queue_name,
            durable=True,
            arguments={"x-dead-letter-exchange": dlx_name},
        )
        return queue_name, dlq_name

    async def publish(
        self,
        queue_name: str,
        message: QueueMessage,
        *,
        retry_count: int = 0,
        priority: int | None = None,
        format: SerializationFormat = SerializationFormat.JSON,
    ) -> None:
        """Publish a message to ``queue_name`` ("Publish" / "Priority Publish").

        On failure, records a "failed" metric before re-raising -- the
        single place this is tracked, since higher-level publishers
        (e.g. :class:`shared_core.events.publisher.EventPublisher`) that
        retry a failed publish call this method again for each attempt.
        """
        try:
            channel = await self.channel()
            body = serialize_message(message, format=format)
            content_type = _CONTENT_TYPE_BY_FORMAT[format]
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=body,
                    content_type=content_type,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    headers={RETRY_COUNT_HEADER: retry_count},
                    priority=priority,
                ),
                routing_key=queue_name,
            )
        except Exception:
            self.statistics.record_failed()
            record_failed(queue_name)
            raise
        self.statistics.record_published()
        record_published(queue_name)

    async def consume(
        self,
        queue_name: str,
        handler: Callable[[QueueMessage], Awaitable[None]],
        *,
        max_retries: int = RabbitMQConstants.DEFAULT_RETRY_MAX_ATTEMPTS,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        """Consume from ``queue_name``, retrying failures with backoff before dead-lettering.

        *retry_policy* governs both the retry ceiling (defaulting to
        *max_retries*, kept as a separate parameter for backward
        compatibility with the Prompt 012 baseline signature) and the
        backoff curve. Every retry is delayed (see module docstring)
        rather than requeued immediately.
        """
        policy = retry_policy or RetryPolicy(max_attempts=max_retries)
        channel = await self.channel()
        queue = await channel.get_queue(queue_name)

        async def _on_message(message: AbstractIncomingMessage) -> None:
            await self._handle_message(message, queue_name, handler, policy)

        await queue.consume(_on_message)

    async def _handle_message(
        self,
        message: AbstractIncomingMessage,
        queue_name: str,
        handler: Callable[[QueueMessage], Awaitable[None]],
        policy: RetryPolicy,
    ) -> None:
        # We always set this header to an int when publishing (see above);
        # aio-pika's header value type is a broad union mypy can't narrow.
        retry_count = int((message.headers or {}).get(RETRY_COUNT_HEADER, 0))  # type: ignore[arg-type]
        format = _FORMAT_BY_CONTENT_TYPE.get(message.content_type or "", SerializationFormat.JSON)
        payload = deserialize_message(message.body, format=format)
        try:
            with measure_processing(queue_name):
                await handler(payload)
        except Exception as exc:
            self.statistics.record_failed()
            record_failed(queue_name)
            await self._retry_or_dead_letter(message, queue_name, payload, retry_count, policy, exc)
            return
        await message.ack()
        self.statistics.record_consumed()
        record_consumed(queue_name)

    async def _retry_or_dead_letter(
        self,
        message: AbstractIncomingMessage,
        queue_name: str,
        payload: QueueMessage,
        retry_count: int,
        policy: RetryPolicy,
        exc: Exception,
    ) -> None:
        will_retry = retry_count < policy.max_attempts and policy.classify(exc)
        if not will_retry:
            await message.reject(requeue=False)
            self.statistics.record_dead_lettered()
            record_dead_lettered(queue_name)
            return

        await message.ack()
        self.statistics.record_retried()
        record_retried(queue_name)
        delay_ms = compute_backoff_delay_ms(
            retry_count + 1,
            base_seconds=policy.backoff_base_seconds,
            max_seconds=policy.backoff_max_seconds,
            multiplier=policy.backoff_multiplier,
        )
        if delay_ms <= 0:
            await self.publish(queue_name, payload, retry_count=retry_count + 1)
            return
        channel = await self.channel()
        holding_name = await declare_delay_queue(channel, queue_name, delay_ms)
        await self.publish(holding_name, payload, retry_count=retry_count + 1)


__all__ = ["QueueManager"]
