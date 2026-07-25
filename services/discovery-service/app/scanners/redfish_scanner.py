"""Redfish scanner, via DMTF's own official ``redfish`` client library.

**Not verified against a real Redfish-capable BMC in this environment**:
Redfish is a server/BMC out-of-band management protocol -- there is no
real (or realistically emulable without a much heavier DMTF Mockup
Server dependency) Redfish-speaking device reachable here. The client
code below is real and complete -- it fetches the Service Root
(``/redfish/v1/``), the same unauthenticated first call every real
Redfish client makes to identify a service before authenticating.
"""

from __future__ import annotations

import asyncio
import time

import redfish
from redfish.rest.v1 import (
    InvalidCredentialsError,
    RetriesExhaustedError,
    ServerDownOrUnreachableError,
)

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ProtocolScanner, ScanCredential, ScanOutcome

_DEFAULT_PORT = 443
_HTTP_ERROR_THRESHOLD = 400


class RedfishScanner(ProtocolScanner):
    """Fetches the Redfish Service Root, and logs in if a credential is supplied."""

    protocol = ProtocolType.REDFISH

    async def probe(
        self,
        address: str,
        *,
        port: int | None,
        timeout_seconds: float,
        credential: ScanCredential | None,
    ) -> ScanOutcome:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._connect, address, port or _DEFAULT_PORT, timeout_seconds, credential
        )

    def _connect(
        self, address: str, port: int, timeout_seconds: float, credential: ScanCredential | None
    ) -> ScanOutcome:
        base_url = f"https://{address}:{port}"
        client = redfish.redfish_client(
            base_url=base_url,
            username=credential.username if credential else None,
            password=credential.password if credential else None,
            timeout=timeout_seconds,
            max_retry=0,
            check_connectivity=False,
        )
        start = time.perf_counter()
        try:
            if credential is not None and credential.username:
                client.login(auth="session")
            response = client.get("/redfish/v1/")
        except InvalidCredentialsError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.AUTH_FAILED, error_message=str(exc))
        except (ServerDownOrUnreachableError, RetriesExhaustedError) as exc:
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))
        finally:
            client.logout()

        latency_ms = (time.perf_counter() - start) * 1000
        if response.status >= _HTTP_ERROR_THRESHOLD:
            return ScanOutcome(
                status=DiscoveryResultStatus.FAILURE,
                latency_ms=latency_ms,
                error_message=f"HTTP {response.status}",
            )
        body = response.dict if isinstance(response.dict, dict) else {}
        return ScanOutcome(
            status=DiscoveryResultStatus.SUCCESS,
            latency_ms=latency_ms,
            identity={
                "product": body.get("Product"),
                "redfish_version": body.get("RedfishVersion"),
                "vendor": body.get("Vendor"),
            },
        )


__all__ = ["RedfishScanner"]
