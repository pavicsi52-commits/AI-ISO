"""Tests for :class:`app.scanners.grpc_scanner.GrpcScanner` against a
real, in-process ``grpc.aio`` server implementing the standard health
service (``grpc_health.v1``'s own reference ``HealthServicer``) this
test module starts itself -- see the scanner's own module docstring.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import grpc
import pytest
import pytest_asyncio
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from app.models.enums import DiscoveryResultStatus
from app.scanners.grpc_scanner import GrpcScanner

_TIMEOUT_SECONDS = 5.0
_PORT = 15051


@pytest_asyncio.fixture
async def grpc_health_server() -> AsyncIterator[health.HealthServicer]:
    server = grpc.aio.server()
    servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(servicer, server)
    server.add_insecure_port(f"127.0.0.1:{_PORT}")
    await server.start()
    try:
        yield servicer
    finally:
        await server.stop(None)


async def test_probe_succeeds_when_serving(grpc_health_server: health.HealthServicer) -> None:
    grpc_health_server.set("", health_pb2.HealthCheckResponse.SERVING)  # overall service status
    outcome = await GrpcScanner().probe(
        "127.0.0.1", port=_PORT, timeout_seconds=_TIMEOUT_SECONDS, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.identity["serving_status"] == "SERVING"


async def test_probe_reports_not_serving(grpc_health_server: health.HealthServicer) -> None:
    grpc_health_server.set("", health_pb2.HealthCheckResponse.NOT_SERVING)
    outcome = await GrpcScanner().probe(
        "127.0.0.1", port=_PORT, timeout_seconds=_TIMEOUT_SECONDS, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.identity["serving_status"] == "NOT_SERVING"


async def test_probe_unreachable_maps_to_unreachable_or_timeout() -> None:
    # grpc.aio's own channel connectivity state machine retries silently
    # against a port nothing listens on rather than failing fast, so a
    # real probe here surfaces as DEADLINE_EXCEEDED (TIMEOUT) as often as
    # UNAVAILABLE (UNREACHABLE) -- both are genuine, correctly-mapped
    # outcomes for "nothing is there"; the UNAVAILABLE mapping itself is
    # verified deterministically below via a mocked stub.
    outcome = await GrpcScanner().probe("127.0.0.1", port=15052, timeout_seconds=1, credential=None)
    assert outcome.status in (
        DiscoveryResultStatus.UNREACHABLE,
        DiscoveryResultStatus.TIMEOUT,
    )


def _rpc_error(code: grpc.StatusCode, details: str) -> grpc.aio.AioRpcError:
    return grpc.aio.AioRpcError(code=code, details=details)


def _fake_health_stub(exc: Exception) -> type:
    class _FakeHealthStub:
        def __init__(self, _channel: object) -> None:
            pass

        async def Check(self, *_args: object, **_kwargs: object) -> None:  # noqa: N802
            raise exc

    return _FakeHealthStub


async def test_probe_deadline_exceeded_maps_to_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        health_pb2_grpc,
        "HealthStub",
        _fake_health_stub(_rpc_error(grpc.StatusCode.DEADLINE_EXCEEDED, "deadline exceeded")),
    )
    outcome = await GrpcScanner().probe(
        "127.0.0.1", port=_PORT, timeout_seconds=_TIMEOUT_SECONDS, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.TIMEOUT


async def test_probe_unavailable_maps_to_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        health_pb2_grpc,
        "HealthStub",
        _fake_health_stub(_rpc_error(grpc.StatusCode.UNAVAILABLE, "unavailable")),
    )
    outcome = await GrpcScanner().probe(
        "127.0.0.1", port=_PORT, timeout_seconds=_TIMEOUT_SECONDS, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.UNREACHABLE
    assert outcome.error_message == "unavailable"


async def test_probe_other_rpc_error_maps_to_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        health_pb2_grpc,
        "HealthStub",
        _fake_health_stub(_rpc_error(grpc.StatusCode.INTERNAL, "internal error")),
    )
    outcome = await GrpcScanner().probe(
        "127.0.0.1", port=_PORT, timeout_seconds=_TIMEOUT_SECONDS, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.FAILURE
    assert outcome.error_message == "internal error"
