"""NTP scanner.

Named ``ntp_scanner.py`` for the same third-party-shadowing reason as
``dns_scanner.py`` (this module imports the third-party ``ntplib``
package).
"""

from __future__ import annotations

import asyncio

import ntplib

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ProtocolScanner, ScanCredential, ScanOutcome

_DEFAULT_PORT = 123


class NtpScanner(ProtocolScanner):
    """Queries an NTP server for its current time/stratum/reference clock."""

    protocol = ProtocolType.NTP

    async def probe(
        self,
        address: str,
        *,
        port: int | None,
        timeout_seconds: float,
        credential: ScanCredential | None,
    ) -> ScanOutcome:
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self._query, address, port, timeout_seconds)
        except ntplib.NTPException as exc:
            return ScanOutcome(status=DiscoveryResultStatus.FAILURE, error_message=str(exc))
        except (TimeoutError, OSError) as exc:
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))

    def _query(self, address: str, port: int | None, timeout_seconds: float) -> ScanOutcome:
        client = ntplib.NTPClient()
        response = client.request(address, port=port or _DEFAULT_PORT, timeout=timeout_seconds)
        return ScanOutcome(
            status=DiscoveryResultStatus.SUCCESS,
            latency_ms=response.delay * 1000,
            identity={
                "stratum": response.stratum,
                "precision": response.precision,
                "ref_id": response.ref_id,
                "offset_seconds": response.offset,
            },
        )


__all__ = ["NtpScanner"]
