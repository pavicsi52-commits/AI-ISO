"""Tests for :class:`app.scanners.ldap_scanner.LdapScanner`.

No local LDAP/Active Directory server exists in this environment (see
this scanner's own module docstring for the protocols with a genuine
local target), and the scanner's own ``ldap3.Connection`` call is
hardcoded to the real (``AUTO_BIND_NO_TLS``) client strategy rather
than ``ldap3.MOCK_SYNC``, so the real response-shaping/error-mapping
logic is exercised by monkeypatching ``ldap3.Connection`` itself to
raise (or return) exactly what a real bind against a real server would.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import ldap3
import pytest
from ldap3.core.exceptions import LDAPBindError, LDAPSocketOpenError

from app.models.enums import DiscoveryResultStatus
from app.scanners.base import ScanCredential
from app.scanners.ldap_scanner import LdapScanner

_TIMEOUT_SECONDS = 5.0


def _fake_server_info() -> MagicMock:
    info = MagicMock()
    info.vendor_name = "OpenLDAP"
    info.vendor_version = "2.6"
    info.supported_ldap_versions = ["3"]
    info.naming_contexts = ["dc=example,dc=com"]
    return info


async def test_probe_succeeds_and_reports_server_info(monkeypatch: pytest.MonkeyPatch) -> None:
    info = _fake_server_info()
    monkeypatch.setattr(ldap3.Server, "info", property(lambda self: info))
    fake_connection = MagicMock(bound=True)
    monkeypatch.setattr(ldap3, "Connection", MagicMock(return_value=fake_connection))

    outcome = await LdapScanner().probe(
        "ldap.example.internal", port=389, timeout_seconds=_TIMEOUT_SECONDS, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.identity["vendor_name"] == "OpenLDAP"
    assert outcome.identity["authenticated"] is True
    fake_connection.unbind.assert_called_once()


async def test_probe_bind_error_maps_to_auth_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*_args: Any, **_kwargs: Any) -> None:
        raise LDAPBindError("invalid credentials")

    monkeypatch.setattr(ldap3, "Connection", _raise)
    credential = ScanCredential(username="cn=admin,dc=example,dc=com", password="wrong")
    outcome = await LdapScanner().probe(
        "ldap.example.internal",
        port=389,
        timeout_seconds=_TIMEOUT_SECONDS,
        credential=credential,
    )
    assert outcome.status == DiscoveryResultStatus.AUTH_FAILED


async def test_probe_socket_open_error_maps_to_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*_args: Any, **_kwargs: Any) -> None:
        raise LDAPSocketOpenError("could not connect")

    monkeypatch.setattr(ldap3, "Connection", _raise)
    outcome = await LdapScanner().probe(
        "ldap.example.internal", port=389, timeout_seconds=_TIMEOUT_SECONDS, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.UNREACHABLE


async def test_probe_os_error_maps_to_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("network unreachable")

    monkeypatch.setattr(ldap3, "Connection", _raise)
    outcome = await LdapScanner().probe(
        "ldap.example.internal", port=389, timeout_seconds=_TIMEOUT_SECONDS, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.UNREACHABLE
