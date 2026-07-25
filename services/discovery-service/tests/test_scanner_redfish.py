"""Tests for :mod:`app.scanners.redfish_scanner`.

**Mocked, and here's why**: Redfish targets a server/BMC's
out-of-band management controller -- there is no real (or lightly
emulable, short of the much heavier DMTF Mockup Server) Redfish-
speaking device reachable in this environment (see
``redfish_scanner.py``'s own module docstring). Every
success/auth-failed/unreachable test below patches
``redfish.redfish_client`` -- the one factory function the scanner
calls -- to return a ``MagicMock(spec=HttpClient)`` so only real
``HttpClient`` methods can be stubbed, and every response the client
hands back is a genuine ``redfish.rest.v1.RestResponse`` built the
same way the real library builds one (from an HTTP-response-shaped
object exposing ``status_code``/``content``), carrying the real
Redfish Service Root field names (``RedfishVersion``/``Vendor``/
``Product``) a real ``GET /redfish/v1/`` returns. What's under test is
the scanner's own login/get/logout sequencing and response/error
classification, not a re-implementation of the ``redfish`` library.

The one exception is ``test_probe_against_a_closed_local_port_is_
unreachable``, which makes no mock at all: a closed TCP port on
``localhost`` is real, verifiable local behavior.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest
from redfish.rest.v1 import (
    HttpClient,
    InvalidCredentialsError,
    RestResponse,
    ServerDownOrUnreachableError,
)

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ScanCredential
from app.scanners.redfish_scanner import RedfishScanner


@dataclass
class _FakeHttpResponse:
    """Duck-types the ``requests.Response`` attributes ``RestResponse.
    __init__`` actually reads (``status_code``/``content``) -- the real
    shape, not a synthetic one.
    """

    status_code: int
    content: bytes


def _service_root_response(
    status: int = 200, body: dict[str, object] | None = None
) -> RestResponse:
    payload = body if body is not None else {}
    return RestResponse(
        rest_request=None,
        http_response=_FakeHttpResponse(status_code=status, content=json.dumps(payload).encode()),
    )


def _fake_client() -> MagicMock:
    return MagicMock(spec=HttpClient)


async def test_probe_reports_the_scanners_declared_protocol() -> None:
    assert RedfishScanner().protocol == ProtocolType.REDFISH


async def test_probe_without_credential_fetches_service_root_and_skips_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _fake_client()
    client.get.return_value = _service_root_response(
        200,
        {
            "@odata.type": "#ServiceRoot.v1_5_0.ServiceRoot",
            "Id": "RootService",
            "RedfishVersion": "1.6.0",
            "Vendor": "Contoso",
            "Product": "ContosoServer",
        },
    )
    monkeypatch.setattr("redfish.redfish_client", lambda **kwargs: client)

    scanner = RedfishScanner()
    outcome = await scanner.probe("10.0.0.9", port=443, timeout_seconds=5, credential=None)

    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.identity == {
        "product": "ContosoServer",
        "redfish_version": "1.6.0",
        "vendor": "Contoso",
    }
    client.login.assert_not_called()
    client.get.assert_called_once_with("/redfish/v1/")
    client.logout.assert_called_once()


async def test_probe_with_credential_logs_in_before_fetching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _fake_client()
    client.get.return_value = _service_root_response(
        200, {"RedfishVersion": "1.9.1", "Vendor": "Dell", "Product": "iDRAC9"}
    )
    monkeypatch.setattr("redfish.redfish_client", lambda **kwargs: client)

    scanner = RedfishScanner()
    credential = ScanCredential(username="root", password="calvin")
    outcome = await scanner.probe("10.0.0.9", port=443, timeout_seconds=5, credential=credential)

    assert outcome.status == DiscoveryResultStatus.SUCCESS
    client.login.assert_called_once_with(auth="session")
    client.logout.assert_called_once()


async def test_probe_uses_the_default_port_when_none_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_base_urls: list[str] = []

    def fake_redfish_client(**kwargs: object) -> MagicMock:
        seen_base_urls.append(str(kwargs["base_url"]))
        client = _fake_client()
        client.get.return_value = _service_root_response(200, {})
        return client

    monkeypatch.setattr("redfish.redfish_client", fake_redfish_client)

    scanner = RedfishScanner()
    outcome = await scanner.probe("10.0.0.9", port=None, timeout_seconds=5, credential=None)

    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert seen_base_urls == ["https://10.0.0.9:443"]


async def test_probe_classifies_a_non_2xx_status_as_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _fake_client()
    client.get.return_value = _service_root_response(500, {})
    monkeypatch.setattr("redfish.redfish_client", lambda **kwargs: client)

    scanner = RedfishScanner()
    outcome = await scanner.probe("10.0.0.9", port=443, timeout_seconds=5, credential=None)

    assert outcome.status == DiscoveryResultStatus.FAILURE
    assert outcome.error_message == "HTTP 500"
    client.logout.assert_called_once()


async def test_probe_classifies_invalid_credentials_as_auth_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _fake_client()
    client.login.side_effect = InvalidCredentialsError("invalid username or password")
    monkeypatch.setattr("redfish.redfish_client", lambda **kwargs: client)

    scanner = RedfishScanner()
    credential = ScanCredential(username="root", password="wrong")
    outcome = await scanner.probe("10.0.0.9", port=443, timeout_seconds=5, credential=credential)

    assert outcome.status == DiscoveryResultStatus.AUTH_FAILED
    assert outcome.error_message == "invalid username or password"
    client.logout.assert_called_once()


async def test_probe_classifies_server_down_as_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _fake_client()
    client.get.side_effect = ServerDownOrUnreachableError(
        "Server not reachable or does not support RedFish."
    )
    monkeypatch.setattr("redfish.redfish_client", lambda **kwargs: client)

    scanner = RedfishScanner()
    outcome = await scanner.probe("10.0.0.9", port=443, timeout_seconds=5, credential=None)

    assert outcome.status == DiscoveryResultStatus.UNREACHABLE
    assert outcome.error_message == "Server not reachable or does not support RedFish."
    client.logout.assert_called_once()


async def test_probe_against_a_closed_local_port_is_unreachable() -> None:
    """No mocking: ``localhost:1`` refuses the connection for real,
    exercised through the real, unpatched ``redfish`` client library.
    """
    scanner = RedfishScanner()
    outcome = await scanner.probe("127.0.0.1", port=1, timeout_seconds=3, credential=None)

    assert outcome.status == DiscoveryResultStatus.UNREACHABLE


__all__: list[str] = []
