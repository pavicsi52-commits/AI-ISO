"""gRPC scanner.

Uses gRPC's own standard health-checking protocol
(``grpc.health.v1.Health``, via the pre-generated stubs in
``grpc-health-checking`` -- no custom ``.proto`` compilation needed)
rather than requiring a service-specific schema, since a generic
discovery probe cannot know any target's custom RPC contract in
advance; a server exposing the standard health service is the
practical, real-world way to make a gRPC endpoint self-describing to a
generic prober.

Verified against a real in-process ``grpc.aio`` server implementing the
standard health service (see ``tests/test_scanner_grpc.py``) -- an
earlier build of this package found the compiled ``grpcio`` C extension
(``cygrpc``) blocked from loading on this development machine by a
Windows Application Control (DLL allow-listing) policy; that constraint
no longer reproduces (``import grpc.aio`` now succeeds cleanly here),
so this scanner is tested live like every other one in this package.
"""

from __future__ import annotations

import time

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ProtocolScanner, ScanCredential, ScanOutcome

_DEFAULT_PORT = 50051


class GrpcScanner(ProtocolScanner):
    """Calls the standard ``grpc.health.v1.Health/Check`` RPC."""

    protocol = ProtocolType.GRPC

    async def probe(
        self,
        address: str,
        *,
        port: int | None,
        timeout_seconds: float,
        credential: ScanCredential | None,
    ) -> ScanOutcome:
        target = f"{address}:{port or _DEFAULT_PORT}"
        start = time.perf_counter()
        try:
            async with grpc.aio.insecure_channel(target) as channel:
                stub = health_pb2_grpc.HealthStub(channel)
                response = await stub.Check(
                    health_pb2.HealthCheckRequest(), timeout=timeout_seconds
                )
        except grpc.aio.AioRpcError as exc:
            if exc.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                return ScanOutcome(status=DiscoveryResultStatus.TIMEOUT)
            if exc.code() == grpc.StatusCode.UNAVAILABLE:
                return ScanOutcome(
                    status=DiscoveryResultStatus.UNREACHABLE, error_message=exc.details()
                )
            return ScanOutcome(status=DiscoveryResultStatus.FAILURE, error_message=exc.details())

        latency_ms = (time.perf_counter() - start) * 1000
        status_name = health_pb2.HealthCheckResponse.ServingStatus.Name(response.status)
        return ScanOutcome(
            status=DiscoveryResultStatus.SUCCESS,
            latency_ms=latency_ms,
            identity={"serving_status": status_name},
        )


__all__ = ["GrpcScanner"]
