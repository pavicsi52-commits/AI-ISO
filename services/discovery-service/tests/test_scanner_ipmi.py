"""Tests for :mod:`app.scanners.ipmi_scanner`.

**Mocked, and here's why**: IPMI targets a server's dedicated
out-of-band BMC -- there is no real (or lightly emulable, short of
substantial extra ``ipmi_sim`` infrastructure) IPMI-speaking device
reachable in this environment (see ``ipmi_scanner.py``'s own module
docstring). Every success/completion-code/auth-failed test below
patches ``pyghmi.ipmi.command.Command`` -- the one class the scanner
constructs -- with a ``MagicMock(spec=Command)`` so only real
``Command`` methods can be stubbed, and every "Get Device ID" response
is the real ``{"netfn", "command", "code", "data"}`` shape
``pyghmi.ipmi.private.session.Session`` actually builds (confirmed by
reading that module directly) with a genuine IPMI spec table 20-2
byte layout (a real IANA manufacturer id, Supermicro's ``10876``), so
what's under test is the scanner's own request construction and
response/error classification, not a re-implementation of ``pyghmi``.
The one real-error-message test (``Incorrect password provided``) is
the exact string ``pyghmi``'s own session layer raises on a rejected
password, confirmed by reading that source directly too.

The one exception is ``test_probe_against_a_closed_local_port_is_
unreachable``, which makes no mock at all: IPMI is UDP-based, and a
closed local UDP port genuinely, verifiably raises ``IpmiException``
via ``pyghmi``'s own real RMCP+ session timeout/retry logic -- no
target BMC is needed to prove that.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from pyghmi.exceptions import IpmiException
from pyghmi.ipmi import command

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ScanCredential
from app.scanners.ipmi_scanner import IpmiScanner

# A real "Get Device ID" response body (IPMI spec table 20-2), 11 bytes
# starting right after the completion code -- byte layout: device id,
# device revision, firmware rev 1 (major), firmware rev 2 (minor),
# ipmi version, additional device support, manufacturer id (3 bytes,
# LSB first -- 0x7C/0x2A/0x00 == 10876, Supermicro's real IANA
# enterprise number), product id (2 bytes, LSB first).
_DEVICE_ID_DATA = [0x20, 0x01, 0x02, 0x19, 0x02, 0xBF, 0x7C, 0x2A, 0x00, 0x0C, 0x00]


def _get_device_id_response(code: int = 0, data: list[int] | None = None) -> dict[str, Any]:
    return {
        "netfn": 0x07,
        "command": 0x01,
        "code": code,
        "data": list(data if data is not None else _DEVICE_ID_DATA),
    }


async def test_probe_without_a_username_fails_before_any_network_call() -> None:
    scanner = IpmiScanner()
    outcome = await scanner.probe("10.0.0.9", port=623, timeout_seconds=5, credential=None)

    assert outcome.status == DiscoveryResultStatus.FAILURE
    assert outcome.error_message == "IPMI requires a credential with a username."


async def test_probe_reports_the_scanners_declared_protocol() -> None:
    assert IpmiScanner().protocol == ProtocolType.IPMI


async def test_probe_parses_a_real_get_device_id_response_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_command = MagicMock(spec=command.Command)
    fake_command.raw_command.return_value = _get_device_id_response()
    construct_calls: list[dict[str, Any]] = []

    def fake_command_ctor(**kwargs: Any) -> MagicMock:
        construct_calls.append(kwargs)
        return fake_command

    monkeypatch.setattr(command, "Command", fake_command_ctor)

    scanner = IpmiScanner()
    credential = ScanCredential(username="ADMIN", password="ADMIN")
    outcome = await scanner.probe("10.0.0.9", port=623, timeout_seconds=5, credential=credential)

    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.identity == {
        "manufacturer_id": 10876,
        "product_id": 12,
        "firmware_version": "2.19",
    }
    assert outcome.latency_ms is not None
    assert construct_calls == [
        {"bmc": "10.0.0.9", "userid": "ADMIN", "password": "ADMIN", "port": 623}
    ]
    fake_command.raw_command.assert_called_once_with(netfn=0x06, command=0x01)


async def test_probe_uses_the_default_port_when_none_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_command = MagicMock(spec=command.Command)
    fake_command.raw_command.return_value = _get_device_id_response()
    construct_calls: list[dict[str, Any]] = []

    def fake_command_ctor(**kwargs: Any) -> MagicMock:
        construct_calls.append(kwargs)
        return fake_command

    monkeypatch.setattr(command, "Command", fake_command_ctor)

    scanner = IpmiScanner()
    credential = ScanCredential(username="ADMIN", password="ADMIN")
    outcome = await scanner.probe("10.0.0.9", port=None, timeout_seconds=5, credential=credential)

    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert construct_calls[0]["port"] == 623


async def test_probe_classifies_a_nonzero_completion_code_as_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_command = MagicMock(spec=command.Command)
    fake_command.raw_command.return_value = _get_device_id_response(code=0xC1)
    monkeypatch.setattr(command, "Command", lambda **kwargs: fake_command)

    scanner = IpmiScanner()
    credential = ScanCredential(username="ADMIN", password="ADMIN")
    outcome = await scanner.probe("10.0.0.9", port=623, timeout_seconds=5, credential=credential)

    assert outcome.status == DiscoveryResultStatus.FAILURE
    assert outcome.error_message == "Get Device ID completion code 193"


async def test_probe_classifies_a_rejected_password_as_auth_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``"Incorrect password provided"`` is the real message
    ``pyghmi.ipmi.private.session.Session`` raises on a rejected
    password (confirmed by reading that module directly).
    """

    def fake_command_ctor(**kwargs: Any) -> MagicMock:
        raise IpmiException("Incorrect password provided")

    monkeypatch.setattr(command, "Command", fake_command_ctor)

    scanner = IpmiScanner()
    credential = ScanCredential(username="ADMIN", password="wrong")
    outcome = await scanner.probe("10.0.0.9", port=623, timeout_seconds=5, credential=credential)

    assert outcome.status == DiscoveryResultStatus.AUTH_FAILED
    assert outcome.error_message == "Incorrect password provided"


async def test_probe_classifies_a_generic_ipmi_exception_as_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_command_ctor(**kwargs: Any) -> MagicMock:
        raise IpmiException("Session no longer connected")

    monkeypatch.setattr(command, "Command", fake_command_ctor)

    scanner = IpmiScanner()
    credential = ScanCredential(username="ADMIN", password="ADMIN")
    outcome = await scanner.probe("10.0.0.9", port=623, timeout_seconds=5, credential=credential)

    assert outcome.status == DiscoveryResultStatus.UNREACHABLE
    assert outcome.error_message == "Session no longer connected"


async def test_probe_against_a_closed_local_port_is_unreachable() -> None:
    """No mocking: a closed local UDP port genuinely fails a real RMCP+
    session establishment attempt through the real, unpatched
    ``pyghmi`` client library.
    """
    scanner = IpmiScanner()
    credential = ScanCredential(username="ADMIN", password="ADMIN")
    outcome = await scanner.probe("127.0.0.1", port=1, timeout_seconds=5, credential=credential)

    assert outcome.status == DiscoveryResultStatus.UNREACHABLE


__all__: list[str] = []
