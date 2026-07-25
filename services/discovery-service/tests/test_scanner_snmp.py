"""Tests for :class:`app.scanners.snmp_scanner.SnmpScanner`.

No real SNMP agent exists in this environment (standing one up needs
``pysnmp.entity``'s full agent-side machinery, an order of magnitude
more setup than the client-only in-process servers used elsewhere in
this suite) -- every branch here is exercised by monkeypatching
``get_cmd``/``UdpTransportTarget.create`` directly, matching this
scanner's own module docstring's precedent for the one exception
(``UdpTransportTarget.create``'s DNS-resolution failure) it already
documents mapping specially.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pysnmp.error import PySnmpError
from pysnmp.hlapi.v3arch.asyncio import UdpTransportTarget

from app.models.enums import DiscoveryResultStatus
from app.scanners import snmp_scanner
from app.scanners.base import ScanCredential
from app.scanners.snmp_scanner import SnmpScanner

_TIMEOUT_SECONDS = 5.0


def _patch_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(UdpTransportTarget, "create", AsyncMock(return_value=MagicMock()))


def _var_binds(value: str) -> list[tuple[Any, Any]]:
    return [(MagicMock(), value)]


async def test_probe_succeeds_and_reports_sys_descr(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_transport(monkeypatch)
    monkeypatch.setattr(
        snmp_scanner,
        "get_cmd",
        AsyncMock(return_value=(None, 0, 0, _var_binds("Linux router 5.15"))),
    )
    outcome = await SnmpScanner().probe(
        "192.0.2.1", port=None, timeout_seconds=_TIMEOUT_SECONDS, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.identity["sys_descr"] == "Linux router 5.15"


async def test_probe_uses_custom_community(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_transport(monkeypatch)
    get_cmd_mock = AsyncMock(return_value=(None, 0, 0, _var_binds("device")))
    monkeypatch.setattr(snmp_scanner, "get_cmd", get_cmd_mock)
    credential = ScanCredential(extra={"community": "private"})
    await SnmpScanner().probe(
        "192.0.2.1", port=None, timeout_seconds=_TIMEOUT_SECONDS, credential=credential
    )
    community_arg = get_cmd_mock.call_args.args[1]
    assert community_arg.communityName == "private"


async def test_probe_error_indication_timeout_maps_to_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(monkeypatch)
    monkeypatch.setattr(
        snmp_scanner, "get_cmd", AsyncMock(return_value=("Request timeout", 0, 0, []))
    )
    outcome = await SnmpScanner().probe(
        "192.0.2.1", port=None, timeout_seconds=_TIMEOUT_SECONDS, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.TIMEOUT


async def test_probe_other_error_indication_maps_to_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(monkeypatch)
    monkeypatch.setattr(snmp_scanner, "get_cmd", AsyncMock(return_value=("noSuchName", 0, 0, [])))
    outcome = await SnmpScanner().probe(
        "192.0.2.1", port=None, timeout_seconds=_TIMEOUT_SECONDS, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.FAILURE


async def test_probe_error_status_maps_to_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_transport(monkeypatch)
    error_status = MagicMock()
    error_status.__bool__ = MagicMock(return_value=True)
    error_status.prettyPrint.return_value = "genErr"
    monkeypatch.setattr(
        snmp_scanner, "get_cmd", AsyncMock(return_value=(None, error_status, 0, []))
    )
    outcome = await SnmpScanner().probe(
        "192.0.2.1", port=None, timeout_seconds=_TIMEOUT_SECONDS, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.FAILURE
    assert outcome.error_message == "genErr"


async def test_probe_transport_creation_failure_maps_to_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        UdpTransportTarget, "create", AsyncMock(side_effect=PySnmpError("name resolution failed"))
    )
    outcome = await SnmpScanner().probe(
        "does-not-resolve.invalid", port=None, timeout_seconds=_TIMEOUT_SECONDS, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.UNREACHABLE
