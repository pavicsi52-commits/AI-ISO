"""Broker connection management.

Per docs/021_Enterprise_Queue_Framework.md.txt "CONNECTION MANAGEMENT":
Connection Pool, Reconnect, Retry, Heartbeat, Health Check, Graceful
Shutdown, TLS, Authentication. Renamed from Prompt 012's ``client.py`` to
match this prompt's own directory listing.
"""

from __future__ import annotations

import asyncio
import ssl

import aio_pika
from aio_pika.abc import AbstractRobustConnection
from aio_pika.pool import Pool

from shared_core.config.settings import RabbitMQSettings
from shared_core.logging.logger import get_logger
from shared_core.queue.constants import (
    DEFAULT_CONNECT_BACKOFF_BASE_SECONDS,
    DEFAULT_CONNECT_BACKOFF_MAX_SECONDS,
    DEFAULT_CONNECT_MAX_ATTEMPTS,
    DEFAULT_CONNECTION_POOL_SIZE,
)
from shared_core.queue.exceptions import ConnectionFailedError
from shared_core.queue.retry import compute_backoff_delay

logger = get_logger("shared_core.queue.connection")


async def create_connection(settings: RabbitMQSettings) -> AbstractRobustConnection:
    """Create a robust (auto-reconnecting) RabbitMQ connection.

    "Reconnect" is automatic: ``connect_robust`` transparently
    re-establishes the connection (and every channel/queue/consumer
    declared on it) after a broker restart or network blip -- no manual
    reconnect logic is needed at any call site. TLS ("Authentication"
    over an encrypted channel) is opt-in via
    ``settings.rabbitmq_tls_enabled``, which already switches the URL
    scheme to ``amqps://`` (see :attr:`RabbitMQSettings.url`); the
    explicit SSL context here is what makes that scheme actually
    negotiate TLS rather than fail with an unhandled scheme.
    """
    ssl_context = ssl.create_default_context() if settings.rabbitmq_tls_enabled else None
    # aio-pika's `connect_robust` stub omits its own `**kwargs: Any` passthrough
    # (which is how `heartbeat` genuinely reaches the underlying AMQP connection
    # parameters at runtime) from its overload signatures.
    return await aio_pika.connect_robust(  # type: ignore[call-overload,no-any-return]
        settings.url,
        heartbeat=settings.rabbitmq_heartbeat_seconds,
        ssl_context=ssl_context,
    )


async def create_connection_with_retry(
    settings: RabbitMQSettings,
    *,
    max_attempts: int = DEFAULT_CONNECT_MAX_ATTEMPTS,
    backoff_base_seconds: float = DEFAULT_CONNECT_BACKOFF_BASE_SECONDS,
    backoff_max_seconds: float = DEFAULT_CONNECT_BACKOFF_MAX_SECONDS,
) -> AbstractRobustConnection:
    """Create a connection, retrying transient failures with exponential backoff.

    Raises:
        ConnectionFailedError: If every retry attempt is exhausted.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await create_connection(settings)
        except Exception as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            delay = compute_backoff_delay(
                attempt, base_seconds=backoff_base_seconds, max_seconds=backoff_max_seconds
            )
            logger.warning(
                "broker connection attempt failed, retrying",
                extra={
                    "extra_fields": {
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "delay_seconds": delay,
                    }
                },
            )
            await asyncio.sleep(delay)
    raise ConnectionFailedError(
        f"Failed to connect to the message broker after {max_attempts} attempt(s)."
    ) from last_error


def create_connection_pool(
    settings: RabbitMQSettings, *, pool_size: int = DEFAULT_CONNECTION_POOL_SIZE
) -> Pool[AbstractRobustConnection]:
    """Build a bounded pool of independent broker connections ("Connection Pool").

    Each connection in the pool is fully independent (its own TCP socket,
    its own heartbeat) -- useful for spreading many concurrent
    producers/consumers across more than one connection, since a single
    connection's channels share one underlying socket.
    """

    async def _connect() -> AbstractRobustConnection:
        return await create_connection(settings)

    return Pool(_connect, max_size=pool_size)


async def wait_for_broker(
    connection: AbstractRobustConnection, *, timeout_seconds: float = 30.0
) -> None:
    """Wait until *connection* is open, or raise if it isn't within *timeout_seconds*.

    "Health Check".

    Raises:
        ConnectionFailedError: If the connection doesn't become ready in time.
    """
    try:
        await asyncio.wait_for(connection.ready(), timeout=timeout_seconds)
    except TimeoutError as exc:
        raise ConnectionFailedError(
            f"Broker connection did not become ready within {timeout_seconds}s."
        ) from exc


async def graceful_shutdown(connection: AbstractRobustConnection) -> None:
    """Close *connection* cleanly. Call once at service shutdown ("Graceful Shutdown")."""
    if not connection.is_closed:
        await connection.close()


__all__ = [
    "create_connection",
    "create_connection_pool",
    "create_connection_with_retry",
    "graceful_shutdown",
    "wait_for_broker",
]
