"""Tests for :class:`app.scanners.graphql_scanner.GraphQLScanner`.

No real GraphQL server exists in this environment's docker-compose
stack (see the scanner's own module docstring for the protocols that
genuinely can be verified live) -- every branch here is exercised with
``pytest-httpx`` against the real request-building/response-validation
logic.
"""

from __future__ import annotations

import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.models.enums import DiscoveryResultStatus
from app.scanners.base import ScanCredential
from app.scanners.graphql_scanner import GraphQLScanner


async def test_probe_succeeds_with_valid_introspection_response(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="http://example.internal/graphql",
        json={"data": {"__schema": {"queryType": {"name": "Query"}}}},
    )
    scanner = GraphQLScanner()
    outcome = await scanner.probe("example.internal", port=None, timeout_seconds=5, credential=None)
    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.identity["query_type_name"] == "Query"


async def test_probe_uses_port_in_url(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="http://example.internal:4000/graphql", json={"data": {}})
    scanner = GraphQLScanner()
    outcome = await scanner.probe("example.internal", port=4000, timeout_seconds=5, credential=None)
    assert outcome.status == DiscoveryResultStatus.SUCCESS


async def test_probe_forwards_bearer_token(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="http://example.internal/graphql", json={"data": {}})
    scanner = GraphQLScanner()
    credential = ScanCredential(token="s3cr3t")
    await scanner.probe("example.internal", port=None, timeout_seconds=5, credential=credential)
    request = httpx_mock.get_requests()[0]
    assert request.headers["authorization"] == "Bearer s3cr3t"


@pytest.mark.parametrize("status_code", [401, 403])
async def test_probe_401_403_map_to_auth_failed(httpx_mock: HTTPXMock, status_code: int) -> None:
    httpx_mock.add_response(url="http://example.internal/graphql", status_code=status_code)
    scanner = GraphQLScanner()
    outcome = await scanner.probe("example.internal", port=None, timeout_seconds=5, credential=None)
    assert outcome.status == DiscoveryResultStatus.AUTH_FAILED


async def test_probe_invalid_json_maps_to_failure(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="http://example.internal/graphql", content=b"not json", status_code=200
    )
    scanner = GraphQLScanner()
    outcome = await scanner.probe("example.internal", port=None, timeout_seconds=5, credential=None)
    assert outcome.status == DiscoveryResultStatus.FAILURE
    assert outcome.error_message == "Response was not valid JSON."


async def test_probe_missing_data_field_maps_to_failure(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="http://example.internal/graphql", json={"errors": [{"message": "nope"}]}
    )
    scanner = GraphQLScanner()
    outcome = await scanner.probe("example.internal", port=None, timeout_seconds=5, credential=None)
    assert outcome.status == DiscoveryResultStatus.FAILURE
    assert outcome.error_message == "Response did not contain a GraphQL 'data' field."


async def test_probe_non_dict_body_maps_to_failure(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="http://example.internal/graphql", json=[1, 2, 3])
    scanner = GraphQLScanner()
    outcome = await scanner.probe("example.internal", port=None, timeout_seconds=5, credential=None)
    assert outcome.status == DiscoveryResultStatus.FAILURE


async def test_probe_timeout(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.TimeoutException("timed out"))
    scanner = GraphQLScanner()
    outcome = await scanner.probe("example.internal", port=None, timeout_seconds=1, credential=None)
    assert outcome.status == DiscoveryResultStatus.TIMEOUT


async def test_probe_unreachable(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    scanner = GraphQLScanner()
    outcome = await scanner.probe("example.internal", port=None, timeout_seconds=1, credential=None)
    assert outcome.status == DiscoveryResultStatus.UNREACHABLE


async def test_probe_generic_http_error_maps_to_failure(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ProtocolError("bad"))
    scanner = GraphQLScanner()
    outcome = await scanner.probe("example.internal", port=None, timeout_seconds=1, credential=None)
    assert outcome.status == DiscoveryResultStatus.FAILURE
