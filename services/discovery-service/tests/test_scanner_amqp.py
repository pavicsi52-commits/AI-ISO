"""Tests for :class:`app.scanners.amqp_scanner.AmqpScanner` against the
real ``aiios_rabbitmq`` docker-compose container, per the scanner's own
module docstring.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import aio_pika
import aiormq
import pytest

from app.models.enums import DiscoveryResultStatus
from app.scanners.amqp_scanner import AmqpScanner
from app.scanners.base import ScanCredential

_TIMEOUT_SECONDS = 5.0


async def test_probe_succeeds_with_real_credentials() -> None:
    credential = ScanCredential(username="aiios", password="change-me", extra={"vhost": "/aiios"})
    outcome = await AmqpScanner().probe(
        "localhost", port=5672, timeout_seconds=_TIMEOUT_SECONDS, credential=credential
    )
    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.identity["vhost"] == "/aiios"
    assert outcome.identity["connected"] is True


async def test_probe_wrong_password_maps_to_auth_failed() -> None:
    credential = ScanCredential(
        username="aiios", password="definitely-wrong", extra={"vhost": "/aiios"}
    )
    outcome = await AmqpScanner().probe(
        "localhost", port=5672, timeout_seconds=_TIMEOUT_SECONDS, credential=credential
    )
    assert outcome.status == DiscoveryResultStatus.AUTH_FAILED


async def test_probe_unreachable_port() -> None:
    outcome = await AmqpScanner().probe("localhost", port=1, timeout_seconds=1, credential=None)
    assert outcome.status in (
        DiscoveryResultStatus.UNREACHABLE,
        DiscoveryResultStatus.TIMEOUT,
    )


async def test_probe_defaults_credential_to_guest() -> None:
    with patch.object(
        aio_pika, "connect_robust", AsyncMock(side_effect=TimeoutError())
    ) as mock_connect:
        outcome = await AmqpScanner().probe(
            "localhost", port=None, timeout_seconds=1, credential=None
        )
    assert outcome.status == DiscoveryResultStatus.TIMEOUT
    _, kwargs = mock_connect.call_args
    assert kwargs["login"] == "guest"
    assert kwargs["password"] == "guest"
    assert kwargs["virtualhost"] == "/"


@pytest.mark.parametrize(
    "exc", [aiormq.exceptions.AMQPConnectionError("refused"), ConnectionError("refused")]
)
async def test_probe_connection_error_maps_to_unreachable(exc: Exception) -> None:
    with patch.object(aio_pika, "connect_robust", AsyncMock(side_effect=exc)):
        outcome = await AmqpScanner().probe(
            "localhost", port=None, timeout_seconds=1, credential=None
        )
    assert outcome.status == DiscoveryResultStatus.UNREACHABLE
