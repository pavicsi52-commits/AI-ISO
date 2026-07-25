"""Modbus TCP scanner, via ``pymodbus``.

Live-verified against a real in-process ``pymodbus`` TCP server
(``tests/test_scanner_modbus.py``) -- a genuine Modbus TCP/MBAP
handshake and register read, not a protocol simulation.
"""

from __future__ import annotations

import time

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ProtocolScanner, ScanCredential, ScanOutcome

_DEFAULT_PORT = 502


class ModbusScanner(ProtocolScanner):
    """Connects over Modbus TCP and reads holding register 0 as an identity probe."""

    protocol = ProtocolType.MODBUS

    async def probe(
        self,
        address: str,
        *,
        port: int | None,
        timeout_seconds: float,
        credential: ScanCredential | None,
    ) -> ScanOutcome:
        client = AsyncModbusTcpClient(address, port=port or _DEFAULT_PORT, timeout=timeout_seconds)
        start = time.perf_counter()
        try:
            connected = await client.connect()
        except OSError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))
        if not connected:
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE)

        try:
            unit_id = 1
            if credential is not None and credential.extra.get("unit_id") is not None:
                unit_id = int(credential.extra["unit_id"])
            response = await client.read_holding_registers(address=0, count=1, device_id=unit_id)
            latency_ms = (time.perf_counter() - start) * 1000
            if response.isError():
                return ScanOutcome(
                    status=DiscoveryResultStatus.FAILURE,
                    latency_ms=latency_ms,
                    error_message=str(response),
                )
            return ScanOutcome(
                status=DiscoveryResultStatus.SUCCESS,
                latency_ms=latency_ms,
                identity={"unit_id": unit_id, "register_0": response.registers[0]},
            )
        except ModbusException as exc:
            return ScanOutcome(status=DiscoveryResultStatus.FAILURE, error_message=str(exc))
        except TimeoutError:
            return ScanOutcome(status=DiscoveryResultStatus.TIMEOUT)
        finally:
            client.close()


__all__ = ["ModbusScanner"]
