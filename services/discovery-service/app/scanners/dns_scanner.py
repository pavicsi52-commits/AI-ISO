"""DNS resolution scanner.

Per docs/037 "NETWORK DISCOVERY": "DNS Resolution." Named
``dns_scanner.py`` (not ``dns.py``) so it never shadows the third-party
``dns`` package (``dnspython``) it imports -- the same submodule-name-
collision discipline every prior AI-IOS service already applies to its
own stdlib/third-party-adjacent module names.
"""

from __future__ import annotations

import time

import dns.asyncresolver
import dns.exception

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ProtocolScanner, ScanCredential, ScanOutcome


class DnsScanner(ProtocolScanner):
    """Resolves *address* as a hostname via a real DNS query (A/AAAA)."""

    protocol = ProtocolType.DNS

    async def probe(
        self,
        address: str,
        *,
        port: int | None,
        timeout_seconds: float,
        credential: ScanCredential | None,
    ) -> ScanOutcome:
        resolver = dns.asyncresolver.Resolver()
        resolver.timeout = timeout_seconds
        resolver.lifetime = timeout_seconds
        start = time.perf_counter()
        try:
            answer = await resolver.resolve(address, "A")
        except dns.resolver.NXDOMAIN:
            return ScanOutcome(
                status=DiscoveryResultStatus.FAILURE, error_message=f"{address!r} does not exist."
            )
        except dns.exception.Timeout:
            return ScanOutcome(status=DiscoveryResultStatus.TIMEOUT)
        except dns.exception.DNSException as exc:
            return ScanOutcome(status=DiscoveryResultStatus.FAILURE, error_message=str(exc))

        latency_ms = (time.perf_counter() - start) * 1000
        addresses = [str(record) for record in answer]
        return ScanOutcome(
            status=DiscoveryResultStatus.SUCCESS,
            latency_ms=latency_ms,
            identity={"addresses": addresses, "ttl": answer.rrset.ttl if answer.rrset else None},
        )


__all__ = ["DnsScanner"]
