"""Tests for :class:`app.scanners.opcua_scanner.OpcUaScanner` against a
real, in-process ``asyncua.Server`` this test module starts itself (see
the scanner's own module docstring).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from asyncua.server.server import Server

from app.models.enums import DiscoveryResultStatus
from app.scanners.opcua_scanner import OpcUaScanner

_TIMEOUT_SECONDS = 5.0
_PORT = 14840


@pytest_asyncio.fixture
async def opcua_server() -> AsyncIterator[None]:
    server = Server()
    await server.init()
    server.set_endpoint(f"opc.tcp://127.0.0.1:{_PORT}/aiios-discovery-test/")
    await server.start()
    try:
        yield
    finally:
        await server.stop()


async def test_probe_succeeds_and_reads_server_status(opcua_server: None) -> None:
    outcome = await OpcUaScanner().probe(
        "127.0.0.1", port=_PORT, timeout_seconds=_TIMEOUT_SECONDS, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.identity["server_state"]
    assert str(_PORT) in outcome.identity["endpoint"]


async def test_probe_unreachable_port() -> None:
    outcome = await OpcUaScanner().probe("127.0.0.1", port=1, timeout_seconds=1, credential=None)
    assert outcome.status in (
        DiscoveryResultStatus.UNREACHABLE,
        DiscoveryResultStatus.TIMEOUT,
    )
