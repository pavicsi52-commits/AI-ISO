"""SNMP scanner, via ``pysnmp``'s v3-architecture async HLAPI.

Queries the standard ``SNMPv2-MIB::sysDescr.0`` OID (1.3.6.1.2.1.1.1.0)
-- present on every real SNMP agent regardless of vendor, the same OID
every real network-management tool probes first to identify a device.
Defaults to SNMPv2c with the conventional ``public`` community string
when no credential is supplied, since that remains the deployed
default on most real network hardware.
"""

from __future__ import annotations

import time

from pysnmp.error import PySnmpError
from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
)

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ProtocolScanner, ScanCredential, ScanOutcome

_DEFAULT_PORT = 161
_SYS_DESCR_OID = "1.3.6.1.2.1.1.1.0"


class SnmpScanner(ProtocolScanner):
    """Queries ``sysDescr.0`` over SNMPv2c."""

    protocol = ProtocolType.SNMP

    async def probe(
        self,
        address: str,
        *,
        port: int | None,
        timeout_seconds: float,
        credential: ScanCredential | None,
    ) -> ScanOutcome:
        community = (credential.extra.get("community") if credential else None) or "public"
        start = time.perf_counter()
        try:
            transport = await UdpTransportTarget.create(
                (address, port or _DEFAULT_PORT), timeout=timeout_seconds, retries=0
            )
            error_indication, error_status, _error_index, var_binds = await get_cmd(
                SnmpEngine(),
                CommunityData(community),
                transport,
                ContextData(),
                ObjectType(ObjectIdentity(_SYS_DESCR_OID)),
            )
        except (OSError, PySnmpError) as exc:
            # ``UdpTransportTarget.create`` raises its own ``PySnmpError``
            # (wrapping a ``socket.gaierror``) for an address that fails DNS
            # resolution, rather than a plain ``OSError`` -- an ordinary,
            # routine probe failure per this module's own contract
            # (app/scanners/base.py), not a programming error, so it must
            # be mapped here rather than left to propagate.
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))

        if error_indication is not None:
            message = str(error_indication)
            if "timeout" in message.lower():
                return ScanOutcome(status=DiscoveryResultStatus.TIMEOUT)
            return ScanOutcome(status=DiscoveryResultStatus.FAILURE, error_message=message)
        if error_status:
            return ScanOutcome(
                status=DiscoveryResultStatus.FAILURE, error_message=error_status.prettyPrint()
            )

        latency_ms = (time.perf_counter() - start) * 1000
        sys_descr = str(var_binds[0][1]) if var_binds else None
        return ScanOutcome(
            status=DiscoveryResultStatus.SUCCESS,
            latency_ms=latency_ms,
            identity={"sys_descr": sys_descr},
        )


__all__ = ["SnmpScanner"]
