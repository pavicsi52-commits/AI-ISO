"""AMQP scanner, via ``aio_pika``.

Live-verified against this repository's own real RabbitMQ container
(``aiios_rabbitmq``) -- a genuine AMQP 0-9-1 connection handshake, the
same broker every other AI-IOS service's own queue framework already
depends on.
"""

from __future__ import annotations

import time

import aio_pika
import aiormq

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ProtocolScanner, ScanCredential, ScanOutcome

_DEFAULT_PORT = 5672
_DEFAULT_VHOST = "/"


class AmqpScanner(ProtocolScanner):
    """Opens (and immediately closes) a real AMQP connection."""

    protocol = ProtocolType.AMQP

    async def probe(
        self,
        address: str,
        *,
        port: int | None,
        timeout_seconds: float,
        credential: ScanCredential | None,
    ) -> ScanOutcome:
        username = (credential.username if credential else None) or "guest"
        password = (credential.password if credential else None) or "guest"
        vhost = (credential.extra.get("vhost") if credential else None) or _DEFAULT_VHOST

        start = time.perf_counter()
        try:
            connection = await aio_pika.connect_robust(
                host=address,
                port=port or _DEFAULT_PORT,
                login=username,
                password=password,
                virtualhost=vhost,
                timeout=timeout_seconds,
            )
        except aiormq.exceptions.ProbableAuthenticationError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.AUTH_FAILED, error_message=str(exc))
        except TimeoutError:
            return ScanOutcome(status=DiscoveryResultStatus.TIMEOUT)
        except (aiormq.exceptions.AMQPError, ConnectionError, OSError) as exc:
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))

        try:
            latency_ms = (time.perf_counter() - start) * 1000
            return ScanOutcome(
                status=DiscoveryResultStatus.SUCCESS,
                latency_ms=latency_ms,
                identity={"vhost": vhost, "connected": not connection.is_closed},
            )
        finally:
            await connection.close()


__all__ = ["AmqpScanner"]
