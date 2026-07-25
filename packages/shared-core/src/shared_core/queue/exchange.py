"""Exchange management.

Per docs/021_Enterprise_Queue_Framework.md.txt "ROUTING": Topic Exchange,
Direct Exchange, Fanout Exchange, Headers Exchange, Configurable Routing.

Exposes a framework-local :class:`ExchangeType` rather than re-exporting
``aio_pika.ExchangeType`` directly -- callers configure routing against
this framework's own vocabulary, not a specific broker client library's,
consistent with docs/021's "Implementation must support provider
abstraction" (RabbitMQ today; Kafka/NATS/Redis Streams are named as
future providers).
"""

from __future__ import annotations

from enum import StrEnum

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractExchange

from shared_core.queue.exceptions import RoutingError


class ExchangeType(StrEnum):
    """The four AMQP exchange types docs/021 "ROUTING" names."""

    TOPIC = "topic"
    DIRECT = "direct"
    FANOUT = "fanout"
    HEADERS = "headers"


_EXCHANGE_TYPE_MAP: dict[ExchangeType, aio_pika.ExchangeType] = {
    ExchangeType.TOPIC: aio_pika.ExchangeType.TOPIC,
    ExchangeType.DIRECT: aio_pika.ExchangeType.DIRECT,
    ExchangeType.FANOUT: aio_pika.ExchangeType.FANOUT,
    ExchangeType.HEADERS: aio_pika.ExchangeType.HEADERS,
}


async def declare_exchange(
    channel: AbstractChannel,
    name: str,
    exchange_type: ExchangeType,
    *,
    durable: bool = True,
) -> AbstractExchange:
    """Declare an exchange of the given type.

    Raises:
        RoutingError: If the broker rejects the declaration (e.g. the
            exchange already exists with a different type).
    """
    try:
        return await channel.declare_exchange(
            name, _EXCHANGE_TYPE_MAP[exchange_type], durable=durable
        )
    except Exception as exc:
        raise RoutingError(f"Failed to declare exchange '{name}' ({exchange_type.value}).") from exc


__all__ = ["ExchangeType", "declare_exchange"]
