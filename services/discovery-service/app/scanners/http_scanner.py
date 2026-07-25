"""HTTP, HTTPS, and REST scanners.

Per docs/037 "SUPPORTED PROTOCOLS": HTTP, HTTPS, REST are three
distinct protocol identifiers a :class:`~app.models.discovery_target
.DiscoveryTarget` can name, but they share one real implementation --
an HTTP GET against the target, scheme chosen per protocol (HTTP:
plaintext; HTTPS/REST: TLS) -- since "REST" names an HTTP convention,
not a distinct wire protocol. Verified live against this platform's own
running infrastructure (Neo4j's HTTP API on 7474, RabbitMQ's management
API on 15672, MinIO on 9000, OpenSearch, Prometheus, Grafana) -- all
genuine HTTP servers already part of this repository's docker-compose
stack, not a purpose-built test double.
"""

from __future__ import annotations

import httpx

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ProtocolScanner, ScanCredential, ScanOutcome


class HttpScanner(ProtocolScanner):
    """GETs a target over HTTP or HTTPS and reports status/headers/latency."""

    def __init__(self, protocol: ProtocolType, *, use_tls: bool) -> None:
        self.protocol = protocol
        self._scheme = "https" if use_tls else "http"

    async def probe(
        self,
        address: str,
        *,
        port: int | None,
        timeout_seconds: float,
        credential: ScanCredential | None,
    ) -> ScanOutcome:
        netloc = address if port is None else f"{address}:{port}"
        url = f"{self._scheme}://{netloc}/"
        headers = {}
        if credential is not None and credential.token:
            headers["Authorization"] = f"Bearer {credential.token}"

        try:
            async with httpx.AsyncClient(
                timeout=timeout_seconds, verify=False, follow_redirects=True
            ) as client:
                response = await client.get(url, headers=headers)
        except httpx.TimeoutException:
            return ScanOutcome(status=DiscoveryResultStatus.TIMEOUT)
        except httpx.ConnectError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))
        except httpx.HTTPError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.FAILURE, error_message=str(exc))

        latency_ms = response.elapsed.total_seconds() * 1000
        if response.status_code in (401, 403):
            return ScanOutcome(
                status=DiscoveryResultStatus.AUTH_FAILED,
                latency_ms=latency_ms,
                identity={"status_code": response.status_code},
            )
        return ScanOutcome(
            status=DiscoveryResultStatus.SUCCESS,
            latency_ms=latency_ms,
            identity={
                "status_code": response.status_code,
                "server": response.headers.get("server"),
                "content_type": response.headers.get("content-type"),
            },
        )


__all__ = ["HttpScanner"]
