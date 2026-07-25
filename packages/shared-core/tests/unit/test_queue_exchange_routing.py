"""Tests for exchange declaration, queue bindings, and topic routing."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import aio_pika
import pytest
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection
from shared_core.queue.bindings import bind_queue, unbind_queue
from shared_core.queue.exceptions import RoutingError
from shared_core.queue.exchange import ExchangeType, declare_exchange
from shared_core.queue.manager import QueueManager
from shared_core.queue.routing import Router, build_routing_key, topic_matches


def _unique(prefix: str) -> str:
    return f"{prefix}.{uuid.uuid4().hex}"


# --- routing.py: pure logic ---


def test_build_routing_key_joins_segments_with_dots() -> None:
    assert build_routing_key("asset", "discovered", "gpu") == "asset.discovered.gpu"


def test_build_routing_key_requires_at_least_one_segment() -> None:
    with pytest.raises(ValueError, match="at least one segment"):
        build_routing_key()


@pytest.mark.parametrize(
    ("pattern", "routing_key", "expected"),
    [
        ("asset.*", "asset.discovered", True),
        ("asset.*", "asset.discovered.gpu", False),
        ("asset.#", "asset.discovered.gpu", True),
        ("asset.#", "asset", True),
        ("*.discovered.*", "asset.discovered.gpu", True),
        ("order.placed", "order.placed", True),
        ("order.placed", "order.shipped", False),
        ("#", "anything.at.all", True),
    ],
)
def test_topic_matches_follows_amqp_wildcard_semantics(
    pattern: str, routing_key: str, expected: bool
) -> None:
    assert topic_matches(pattern, routing_key) is expected


def test_router_resolve_fans_out_to_every_matching_rule() -> None:
    router = Router()
    router.add_rule("asset.*", "asset-queue")
    router.add_rule("#", "audit-queue")

    assert router.resolve("asset.discovered") == ["asset-queue", "audit-queue"]
    assert router.resolve("order.placed") == ["audit-queue"]


def test_router_clear_removes_every_rule() -> None:
    router = Router()
    router.add_rule("#", "queue")

    router.clear()

    assert router.resolve("anything") == []


# --- exchange.py / bindings.py (real RabbitMQ) ---


@pytest.mark.parametrize(
    "exchange_type",
    [ExchangeType.TOPIC, ExchangeType.DIRECT, ExchangeType.FANOUT, ExchangeType.HEADERS],
)
async def test_declare_exchange_supports_every_amqp_exchange_type(
    rabbitmq_connection: AbstractRobustConnection, exchange_type: ExchangeType
) -> None:
    channel = await rabbitmq_connection.channel()

    exchange = await declare_exchange(channel, _unique("exchange"), exchange_type)

    assert exchange.name


async def test_declare_exchange_wraps_a_broker_failure(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    channel = await rabbitmq_connection.channel()
    name = _unique("exchange")
    await declare_exchange(channel, name, ExchangeType.TOPIC)

    # Re-declaring the same exchange name with a different type is a
    # protocol-level PRECONDITION_FAILED -- a genuine broker rejection.
    channel2 = await rabbitmq_connection.channel()
    with pytest.raises(RoutingError):
        await declare_exchange(channel2, name, ExchangeType.FANOUT)


async def test_bind_and_unbind_queue_to_a_topic_exchange(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    channel = await rabbitmq_connection.channel()
    exchange = await declare_exchange(channel, _unique("exchange"), ExchangeType.TOPIC)
    queue = await channel.declare_queue(_unique("queue"), durable=True)

    await bind_queue(queue, exchange, routing_key="asset.*")

    received: list[bytes] = []

    async def _on_message(message: AbstractIncomingMessage) -> None:
        async with message.process():
            received.append(message.body)

    await queue.consume(_on_message)
    await exchange.publish(aio_pika.Message(body=b"hello"), routing_key="asset.discovered")

    for _ in range(50):
        if received:
            break
        await asyncio.sleep(0.1)
    assert received == [b"hello"]

    await unbind_queue(queue, exchange, routing_key="asset.*")


async def test_unbind_queue_wraps_a_broker_failure() -> None:
    """AMQP's own ``queue.unbind`` is lenient about already-gone bindings, so this
    exercises the wrapping logic directly against a stand-in that raises.
    """

    class _ExplodingQueue:
        name = "stub-queue"

        async def unbind(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("channel closed")

    with pytest.raises(RoutingError):
        await unbind_queue(_ExplodingQueue(), _ExplodingQueue(), routing_key="asset.*")  # type: ignore[arg-type]


async def test_queue_manager_default_exchange_publish_still_works_alongside_custom_exchanges(
    rabbitmq_connection: AbstractRobustConnection,
) -> None:
    """Custom exchange declarations must not interfere with QueueManager's own default-exchange."""
    queue_manager = QueueManager(rabbitmq_connection)
    queue_name = _unique("queue")
    await queue_manager.declare_queue_with_dlq(queue_name)

    received: list[dict[str, Any]] = []

    async def handler(message: dict[str, Any]) -> None:
        received.append(message)

    await queue_manager.consume(queue_name, handler)
    await queue_manager.publish(queue_name, {"ok": True})

    for _ in range(50):
        if received:
            break
        await asyncio.sleep(0.1)
    assert received == [{"ok": True}]
