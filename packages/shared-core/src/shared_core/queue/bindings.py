"""Queue-to-exchange binding management.

Per docs/021_Enterprise_Queue_Framework.md.txt "ROUTING". Kept separate
from :mod:`shared_core.queue.exchange` (which only declares exchanges)
so binding/unbinding a queue -- including with headers-match arguments,
which have no equivalent concept for a plain routing key -- has one
clear home.
"""

from __future__ import annotations

from typing import Any

from aio_pika.abc import AbstractExchange, AbstractQueue

from shared_core.queue.exceptions import RoutingError


async def bind_queue(
    queue: AbstractQueue,
    exchange: AbstractExchange,
    *,
    routing_key: str = "",
    arguments: dict[str, Any] | None = None,
) -> None:
    """Bind *queue* to *exchange* under *routing_key* (or *arguments*, for a headers exchange).

    Raises:
        RoutingError: If the broker rejects the binding.
    """
    try:
        await queue.bind(exchange, routing_key=routing_key, arguments=arguments)
    except Exception as exc:
        raise RoutingError(
            f"Failed to bind queue '{queue.name}' to exchange '{exchange.name}'."
        ) from exc


async def unbind_queue(
    queue: AbstractQueue,
    exchange: AbstractExchange,
    *,
    routing_key: str = "",
    arguments: dict[str, Any] | None = None,
) -> None:
    """Remove a previously-created binding between *queue* and *exchange*.

    Raises:
        RoutingError: If the broker rejects the unbind.
    """
    try:
        await queue.unbind(exchange, routing_key=routing_key, arguments=arguments)
    except Exception as exc:
        raise RoutingError(
            f"Failed to unbind queue '{queue.name}' from exchange '{exchange.name}'."
        ) from exc


__all__ = ["bind_queue", "unbind_queue"]
