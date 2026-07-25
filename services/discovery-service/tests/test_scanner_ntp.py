"""Tests for :class:`app.scanners.ntp_scanner.NtpScanner`.

The success path is verified against a real, well-known public NTP
server (this machine has real internet access, per this package's own
``tests/conftest.py`` module docstring -- ``time.google.com`` specifically,
since this sandbox's outbound UDP egress is unreliable enough that the
``pool.ntp.org`` round-robin and ``time.cloudflare.com`` don't reliably
respond, confirmed by direct reproduction outside pytest). Even
``time.google.com`` occasionally drops a single UDP datagram under this
sandbox's own network conditions (not an application bug), so the
success test retries a handful of times before failing. The exception-
mapping branches are exercised by mocking ``ntplib.NTPClient.request``
directly, since a live query can't deterministically reproduce a
malformed-response or an unreachable-host condition.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import ntplib

from app.models.enums import DiscoveryResultStatus
from app.scanners.ntp_scanner import NtpScanner

_TIMEOUT_SECONDS = 5.0
_MAX_ATTEMPTS = 3


async def test_probe_succeeds_against_real_ntp_server() -> None:
    outcome = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        outcome = await NtpScanner().probe(
            "time.google.com", port=None, timeout_seconds=_TIMEOUT_SECONDS, credential=None
        )
        if outcome.status == DiscoveryResultStatus.SUCCESS or attempt == _MAX_ATTEMPTS:
            break
        await asyncio.sleep(1)
    assert outcome is not None
    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.latency_ms is not None
    assert isinstance(outcome.identity["stratum"], int)


async def test_probe_ntp_exception_maps_to_failure() -> None:
    with patch.object(
        ntplib.NTPClient, "request", side_effect=ntplib.NTPException("malformed reply")
    ):
        outcome = await NtpScanner().probe(
            "example.com", port=None, timeout_seconds=_TIMEOUT_SECONDS, credential=None
        )
    assert outcome.status == DiscoveryResultStatus.FAILURE
    assert outcome.error_message is not None


async def test_probe_os_error_maps_to_unreachable() -> None:
    with patch.object(ntplib.NTPClient, "request", side_effect=OSError("no route to host")):
        outcome = await NtpScanner().probe(
            "example.com", port=None, timeout_seconds=_TIMEOUT_SECONDS, credential=None
        )
    assert outcome.status == DiscoveryResultStatus.UNREACHABLE


async def test_probe_timeout_error_maps_to_unreachable() -> None:
    with patch.object(ntplib.NTPClient, "request", side_effect=TimeoutError()):
        outcome = await NtpScanner().probe(
            "example.com", port=None, timeout_seconds=_TIMEOUT_SECONDS, credential=None
        )
    assert outcome.status == DiscoveryResultStatus.UNREACHABLE
