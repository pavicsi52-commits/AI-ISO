"""Tests for :class:`app.scanners.jmx_scanner.JmxScanner`.

No real Jolokia-instrumented JVM exists in this environment (see the
scanner's own module docstring) -- every branch here is exercised with
``pytest-httpx`` against the real request-building/response-parsing
logic.
"""

from __future__ import annotations

import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.models.enums import DiscoveryResultStatus
from app.scanners.base import ScanCredential
from app.scanners.jmx_scanner import JmxScanner

_TIMEOUT_SECONDS = 5.0


async def test_probe_succeeds_with_valid_jolokia_response(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="http://example.internal:8778/jolokia/version",
        json={"value": {"agent": "1.7.1", "protocol": "7.2", "info": {"product": "tomcat"}}},
    )
    outcome = await JmxScanner().probe(
        "example.internal", port=None, timeout_seconds=_TIMEOUT_SECONDS, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.identity["agent_version"] == "1.7.1"
    assert outcome.identity["protocol_version"] == "7.2"
    assert outcome.identity["jvm_info"] == {"product": "tomcat"}


async def test_probe_uses_custom_port(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="http://example.internal:9999/jolokia/version", json={"value": {}})
    outcome = await JmxScanner().probe(
        "example.internal", port=9999, timeout_seconds=_TIMEOUT_SECONDS, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.SUCCESS


async def test_probe_forwards_basic_auth(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="http://example.internal:8778/jolokia/version", json={"value": {}})
    credential = ScanCredential(username="jmx-user", password="jmx-pass")
    await JmxScanner().probe(
        "example.internal", port=None, timeout_seconds=_TIMEOUT_SECONDS, credential=credential
    )
    request = httpx_mock.get_requests()[0]
    assert request.headers["authorization"].startswith("Basic ")


@pytest.mark.parametrize("status_code", [401, 403])
async def test_probe_401_403_map_to_auth_failed(httpx_mock: HTTPXMock, status_code: int) -> None:
    httpx_mock.add_response(
        url="http://example.internal:8778/jolokia/version", status_code=status_code
    )
    outcome = await JmxScanner().probe(
        "example.internal", port=None, timeout_seconds=_TIMEOUT_SECONDS, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.AUTH_FAILED


async def test_probe_invalid_json_maps_to_failure(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="http://example.internal:8778/jolokia/version", content=b"not json")
    outcome = await JmxScanner().probe(
        "example.internal", port=None, timeout_seconds=_TIMEOUT_SECONDS, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.FAILURE
    assert outcome.error_message == "Response was not valid Jolokia JSON."


async def test_probe_timeout(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.TimeoutException("timed out"))
    outcome = await JmxScanner().probe(
        "example.internal", port=None, timeout_seconds=1, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.TIMEOUT


async def test_probe_unreachable(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    outcome = await JmxScanner().probe(
        "example.internal", port=None, timeout_seconds=1, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.UNREACHABLE


async def test_probe_generic_http_error_maps_to_failure(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ProtocolError("bad"))
    outcome = await JmxScanner().probe(
        "example.internal", port=None, timeout_seconds=1, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.FAILURE
