"""Tests for :class:`app.scanners.ftp_scanner.FtpScanner` against a
real, local ``pyftpdlib`` server this test module starts itself (see
the scanner's own module docstring).
"""

from __future__ import annotations

import tempfile
import threading
from collections.abc import Iterator

import pytest
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer

from app.models.enums import DiscoveryResultStatus
from app.scanners.base import ScanCredential
from app.scanners.ftp_scanner import FtpScanner

_TIMEOUT_SECONDS = 5.0
_USERNAME = "aiios-test"
_PASSWORD = "aiios-test-pass"


@pytest.fixture(scope="module")
def ftp_server() -> Iterator[tuple[str, int]]:
    with tempfile.TemporaryDirectory() as home:
        authorizer = DummyAuthorizer()
        authorizer.add_user(_USERNAME, _PASSWORD, home, perm="elr")
        authorizer.add_anonymous(home)
        handler = FTPHandler
        handler.authorizer = authorizer
        server = FTPServer(("127.0.0.1", 0), handler)
        host, port = server.address

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield host, port
        finally:
            server.close_all()


async def test_probe_anonymous_login_succeeds(ftp_server: tuple[str, int]) -> None:
    host, port = ftp_server
    outcome = await FtpScanner().probe(
        host, port=port, timeout_seconds=_TIMEOUT_SECONDS, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.identity["welcome"]
    assert outcome.identity["system"]


async def test_probe_named_credential_succeeds(ftp_server: tuple[str, int]) -> None:
    host, port = ftp_server
    credential = ScanCredential(username=_USERNAME, password=_PASSWORD)
    outcome = await FtpScanner().probe(
        host, port=port, timeout_seconds=_TIMEOUT_SECONDS, credential=credential
    )
    assert outcome.status == DiscoveryResultStatus.SUCCESS


async def test_probe_wrong_password_maps_to_auth_failed(ftp_server: tuple[str, int]) -> None:
    host, port = ftp_server
    credential = ScanCredential(username=_USERNAME, password="wrong")
    outcome = await FtpScanner().probe(
        host, port=port, timeout_seconds=_TIMEOUT_SECONDS, credential=credential
    )
    assert outcome.status == DiscoveryResultStatus.AUTH_FAILED
    assert outcome.identity["welcome"]


async def test_probe_unreachable_port() -> None:
    outcome = await FtpScanner().probe("127.0.0.1", port=1, timeout_seconds=1, credential=None)
    assert outcome.status in (
        DiscoveryResultStatus.UNREACHABLE,
        DiscoveryResultStatus.TIMEOUT,
    )
