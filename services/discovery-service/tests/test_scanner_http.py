"""Tests for :class:`app.scanners.http_scanner.HttpScanner`.

The success/auth-failed/unreachable branches are verified against this
platform's own real docker-compose infrastructure (Neo4j's HTTP API on
7474, MinIO's console on 9000 -- which genuinely returns ``403`` with
no credentials), per the scanner's own module docstring. The
timeout/generic-HTTPError branches and credential-header forwarding,
which no currently-running local service can deterministically
reproduce, are exercised with ``pytest-httpx``.
"""

from __future__ import annotations

import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ScanCredential
from app.scanners.http_scanner import HttpScanner


async def test_probe_succeeds_against_real_neo4j_http_api() -> None:
    scanner = HttpScanner(ProtocolType.HTTP, use_tls=False)
    outcome = await scanner.probe("localhost", port=7474, timeout_seconds=5, credential=None)
    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.identity["status_code"] == 200
    assert outcome.latency_ms is not None


async def test_probe_auth_failed_against_real_minio_console() -> None:
    scanner = HttpScanner(ProtocolType.HTTP, use_tls=False)
    outcome = await scanner.probe("localhost", port=9000, timeout_seconds=5, credential=None)
    assert outcome.status == DiscoveryResultStatus.AUTH_FAILED
    assert outcome.identity["status_code"] == 403


async def test_probe_unreachable_port() -> None:
    scanner = HttpScanner(ProtocolType.HTTP, use_tls=False)
    outcome = await scanner.probe("localhost", port=1, timeout_seconds=2, credential=None)
    assert outcome.status in (
        DiscoveryResultStatus.UNREACHABLE,
        DiscoveryResultStatus.TIMEOUT,
    )


async def test_probe_https_uses_tls_scheme(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="https://example.internal:8443/", status_code=200)
    scanner = HttpScanner(ProtocolType.HTTPS, use_tls=True)
    outcome = await scanner.probe("example.internal", port=8443, timeout_seconds=5, credential=None)
    assert outcome.status == DiscoveryResultStatus.SUCCESS


async def test_probe_forwards_bearer_token(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="http://example.internal/", status_code=200)
    scanner = HttpScanner(ProtocolType.REST, use_tls=False)
    credential = ScanCredential(token="s3cr3t")
    await scanner.probe("example.internal", port=None, timeout_seconds=5, credential=credential)
    request = httpx_mock.get_requests()[0]
    assert request.headers["authorization"] == "Bearer s3cr3t"


async def test_probe_timeout(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.TimeoutException("timed out"))
    scanner = HttpScanner(ProtocolType.HTTP, use_tls=False)
    outcome = await scanner.probe("example.internal", port=None, timeout_seconds=1, credential=None)
    assert outcome.status == DiscoveryResultStatus.TIMEOUT


async def test_probe_generic_http_error_maps_to_failure(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ProtocolError("bad response"))
    scanner = HttpScanner(ProtocolType.HTTP, use_tls=False)
    outcome = await scanner.probe("example.internal", port=None, timeout_seconds=1, credential=None)
    assert outcome.status == DiscoveryResultStatus.FAILURE


@pytest.mark.parametrize("status_code", [401, 403])
async def test_probe_401_403_map_to_auth_failed(httpx_mock: HTTPXMock, status_code: int) -> None:
    httpx_mock.add_response(status_code=status_code)
    scanner = HttpScanner(ProtocolType.HTTP, use_tls=False)
    outcome = await scanner.probe("example.internal", port=None, timeout_seconds=5, credential=None)
    assert outcome.status == DiscoveryResultStatus.AUTH_FAILED
