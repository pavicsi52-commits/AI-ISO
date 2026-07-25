"""Tests for :class:`app.scanners.modbus_scanner.ModbusScanner` against
a real, in-process ``pymodbus`` TCP server this test module starts
itself (see the scanner's own module docstring).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from pymodbus.datastore import ModbusDeviceContext, ModbusSequentialDataBlock, ModbusServerContext
from pymodbus.server import ModbusTcpServer

from app.models.enums import DiscoveryResultStatus
from app.scanners.base import ScanCredential
from app.scanners.modbus_scanner import ModbusScanner

_TIMEOUT_SECONDS = 5.0
_PORT = 15020
_REGISTER_0_VALUE = 4242


@pytest_asyncio.fixture
async def modbus_server() -> AsyncIterator[None]:
    # ModbusSequentialDataBlock's own address param is 1-based internally
    # (it computes `address - 1` as the real offset), so register 0 needs
    # address=1 here -- and its __init__ leaves its params untyped.
    data_block = ModbusSequentialDataBlock(1, [_REGISTER_0_VALUE, 0, 0, 0])  # type: ignore[no-untyped-call]
    device = ModbusDeviceContext(hr=data_block)
    context = ModbusServerContext(devices={1: device}, single=False)
    server = ModbusTcpServer(context, address=("127.0.0.1", _PORT))
    await server.serve_forever(background=True)
    try:
        yield
    finally:
        await server.shutdown()  # type: ignore[no-untyped-call]


async def test_probe_succeeds_and_reads_register_0(modbus_server: None) -> None:
    outcome = await ModbusScanner().probe(
        "127.0.0.1", port=_PORT, timeout_seconds=_TIMEOUT_SECONDS, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.identity["unit_id"] == 1
    assert outcome.identity["register_0"] == _REGISTER_0_VALUE


async def test_probe_uses_credential_unit_id(modbus_server: None) -> None:
    credential = ScanCredential(extra={"unit_id": 1})
    outcome = await ModbusScanner().probe(
        "127.0.0.1",
        port=_PORT,
        timeout_seconds=_TIMEOUT_SECONDS,
        credential=credential,
    )
    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.identity["unit_id"] == 1


async def test_probe_unknown_unit_id_is_error_response(modbus_server: None) -> None:
    credential = ScanCredential(extra={"unit_id": 99})
    outcome = await ModbusScanner().probe(
        "127.0.0.1",
        port=_PORT,
        timeout_seconds=_TIMEOUT_SECONDS,
        credential=credential,
    )
    assert outcome.status == DiscoveryResultStatus.FAILURE


async def test_probe_unreachable_port() -> None:
    outcome = await ModbusScanner().probe("127.0.0.1", port=1, timeout_seconds=1, credential=None)
    assert outcome.status == DiscoveryResultStatus.UNREACHABLE
