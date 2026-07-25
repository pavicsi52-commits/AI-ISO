"""IPMI scanner, via ``pyghmi`` (the IPMI client OpenStack's ``ironic``
project itself uses).

**Not verified against a real BMC in this environment**: IPMI targets
a server's dedicated out-of-band management controller -- there is no
real (or lightly emulable -- OpenIPMI's ``ipmi_sim`` is a substantial
additional dependency) IPMI-speaking BMC reachable here. The client
code below is real and complete -- a genuine RMCP+ session
establishment (UDP 623) followed by a Get Device ID command, the same
minimal identifying command every real IPMI tool (``ipmitool mc info``)
issues first.
"""

from __future__ import annotations

import asyncio
import time

from pyghmi.exceptions import IpmiException
from pyghmi.ipmi import command

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ProtocolScanner, ScanCredential, ScanOutcome

_DEFAULT_PORT = 623
_NETFN_APP_REQUEST = 0x06
_CMD_GET_DEVICE_ID = 0x01


def _parse_device_id(data: bytes) -> dict[str, object]:
    """Parse the IPMI "Get Device ID" response body (IPMI spec table 20-2)."""
    manufacturer_id = data[6] | (data[7] << 8) | ((data[8] & 0x0F) << 16)
    product_id = data[9] | (data[10] << 8)
    firmware_major = data[2] & 0x7F
    firmware_minor = data[3]
    return {
        "manufacturer_id": manufacturer_id,
        "product_id": product_id,
        "firmware_version": f"{firmware_major}.{firmware_minor:02x}",
    }


class IpmiScanner(ProtocolScanner):
    """Establishes an RMCP+ session and issues Get Device ID."""

    protocol = ProtocolType.IPMI

    async def probe(
        self,
        address: str,
        *,
        port: int | None,
        timeout_seconds: float,
        credential: ScanCredential | None,
    ) -> ScanOutcome:
        if credential is None or not credential.username:
            return ScanOutcome(
                status=DiscoveryResultStatus.FAILURE,
                error_message="IPMI requires a credential with a username.",
            )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._connect, address, port or _DEFAULT_PORT, credential
        )

    def _connect(self, address: str, port: int, credential: ScanCredential) -> ScanOutcome:
        start = time.perf_counter()
        try:
            ipmi_command = command.Command(
                bmc=address,
                userid=credential.username,
                password=credential.password or "",
                port=port,
            )
            response = ipmi_command.raw_command(
                netfn=_NETFN_APP_REQUEST, command=_CMD_GET_DEVICE_ID
            )
        except IpmiException as exc:
            message = str(exc)
            if "password" in message.lower() or "unauthorized" in message.lower():
                return ScanOutcome(status=DiscoveryResultStatus.AUTH_FAILED, error_message=message)
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=message)

        latency_ms = (time.perf_counter() - start) * 1000
        if response.get("code"):
            return ScanOutcome(
                status=DiscoveryResultStatus.FAILURE,
                latency_ms=latency_ms,
                error_message=f"Get Device ID completion code {response['code']}",
            )
        return ScanOutcome(
            status=DiscoveryResultStatus.SUCCESS,
            latency_ms=latency_ms,
            identity=_parse_device_id(bytes(response["data"])),
        )


__all__ = ["IpmiScanner"]
