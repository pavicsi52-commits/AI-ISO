"""Tests for :mod:`app.scanners.smb_scanner`.

**Mocked, and here's why**: no Samba/Windows file-sharing server is
reachable in this environment (see ``smb_scanner.py``'s own module
docstring -- standing one up would need a full Samba container plus
user provisioning, a heavier dependency than this one protocol among
many in this package justifies). Every success/auth-failed/protocol-
error test below patches ``smbclient.register_session``/``listdir``/
``reset_connection_cache`` -- the exact ``smbclient`` module-level
functions the scanner itself calls -- with the real
``smbprotocol.exceptions`` types and real ``listdir`` return shape
(``list[str]`` of entry names, confirmed by reading
``smbclient._os.listdir`` directly), so what's under test is the
scanner's own call construction and response/error classification.

The one exception is ``test_probe_against_a_closed_local_port_is_
unreachable``, which makes no mock at all: a closed TCP port on
``localhost`` is real, verifiable local behavior. It also happens to
be the real regression case this test file's own authoring caught
live: ``smbprotocol.transport.Tcp.connect()`` wraps a genuine refused
connection in a bare ``ValueError`` (not ``SMBException``, not
``OSError``) -- ``smb_scanner.py`` now has an explicit
``except ValueError`` clause for exactly this.
"""

from __future__ import annotations

from typing import Any

import pytest
from smbprotocol.exceptions import LogonFailure, SMBException

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ScanCredential
from app.scanners.smb_scanner import SmbScanner

_IPC_ENTRIES = ["srvsvc", "wkssvc", "lsarpc"]


async def test_probe_reports_the_scanners_declared_protocol() -> None:
    assert SmbScanner().protocol == ProtocolType.SMB


async def test_probe_negotiates_a_session_and_lists_ipc_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercises the scanner's own request-building end to end: a real
    UNC path is passed to ``listdir`` for the ``IPC$`` share, and the
    session is registered with the credential's own username/password.
    """
    register_calls: list[dict[str, Any]] = []
    listdir_calls: list[str] = []
    reset_calls: list[object] = []

    def fake_register_session(server: str, **kwargs: Any) -> None:
        register_calls.append({"server": server, **kwargs})

    def fake_listdir(path: str, **kwargs: Any) -> list[str]:
        listdir_calls.append(path)
        return list(_IPC_ENTRIES)

    def fake_reset_connection_cache(**kwargs: Any) -> None:
        reset_calls.append(kwargs.get("connection_cache"))

    monkeypatch.setattr("smbclient.register_session", fake_register_session)
    monkeypatch.setattr("smbclient.listdir", fake_listdir)
    monkeypatch.setattr("smbclient.reset_connection_cache", fake_reset_connection_cache)

    scanner = SmbScanner()
    credential = ScanCredential(username="administrator", password="s3cret")
    outcome = await scanner.probe(
        "fileserver.example.com", port=445, timeout_seconds=5, credential=credential
    )

    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.identity == {"ipc_entry_count": len(_IPC_ENTRIES)}
    assert outcome.latency_ms is not None
    assert register_calls == [
        {
            "server": "fileserver.example.com",
            "username": "administrator",
            "password": "s3cret",
            "port": 445,
            "connection_timeout": 5,
            "connection_cache": register_calls[0]["connection_cache"],
        }
    ]
    assert listdir_calls == [r"\\fileserver.example.com\IPC$"]
    assert len(reset_calls) == 1


async def test_probe_uses_the_default_port_when_none_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_ports: list[int] = []

    def fake_register_session(server: str, **kwargs: Any) -> None:
        seen_ports.append(kwargs["port"])

    def fake_listdir(path: str, **kwargs: Any) -> list[str]:
        return []

    def fake_reset_connection_cache(**kwargs: Any) -> None:
        pass

    monkeypatch.setattr("smbclient.register_session", fake_register_session)
    monkeypatch.setattr("smbclient.listdir", fake_listdir)
    monkeypatch.setattr("smbclient.reset_connection_cache", fake_reset_connection_cache)

    scanner = SmbScanner()
    outcome = await scanner.probe(
        "fileserver.example.com", port=None, timeout_seconds=5, credential=None
    )

    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert seen_ports == [445]


async def test_probe_classifies_a_logon_failure_as_auth_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real, zero-argument ``LogonFailure()`` already carries the
    genuine NT status message (see ``smbprotocol.exceptions
    .SMBResponseException``'s own ``_BASE_MESSAGE``).
    """

    def fake_register_session(server: str, **kwargs: Any) -> None:
        raise LogonFailure()

    def fake_reset_connection_cache(**kwargs: Any) -> None:
        pass

    monkeypatch.setattr("smbclient.register_session", fake_register_session)
    monkeypatch.setattr("smbclient.reset_connection_cache", fake_reset_connection_cache)

    scanner = SmbScanner()
    credential = ScanCredential(username="administrator", password="wrong")
    outcome = await scanner.probe(
        "fileserver.example.com", port=445, timeout_seconds=5, credential=credential
    )

    assert outcome.status == DiscoveryResultStatus.AUTH_FAILED
    assert outcome.error_message is not None
    assert "logon is invalid" in outcome.error_message.lower()


async def test_probe_classifies_a_protocol_error_as_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_register_session(server: str, **kwargs: Any) -> None:
        pass

    def fake_listdir(path: str, **kwargs: Any) -> list[str]:
        raise SMBException("STATUS_ACCESS_DENIED listing IPC$")

    def fake_reset_connection_cache(**kwargs: Any) -> None:
        pass

    monkeypatch.setattr("smbclient.register_session", fake_register_session)
    monkeypatch.setattr("smbclient.listdir", fake_listdir)
    monkeypatch.setattr("smbclient.reset_connection_cache", fake_reset_connection_cache)

    scanner = SmbScanner()
    credential = ScanCredential(username="administrator", password="s3cret")
    outcome = await scanner.probe(
        "fileserver.example.com", port=445, timeout_seconds=5, credential=credential
    )

    assert outcome.status == DiscoveryResultStatus.FAILURE
    assert outcome.error_message == "STATUS_ACCESS_DENIED listing IPC$"


async def test_probe_classifies_a_dropped_connection_as_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bare ``OSError`` mid-session (e.g. the peer resets the TCP
    connection while listing) is also classified as ``UNREACHABLE``.
    """

    def fake_register_session(server: str, **kwargs: Any) -> None:
        pass

    def fake_listdir(path: str, **kwargs: Any) -> list[str]:
        raise ConnectionResetError("[Errno 104] Connection reset by peer")

    def fake_reset_connection_cache(**kwargs: Any) -> None:
        pass

    monkeypatch.setattr("smbclient.register_session", fake_register_session)
    monkeypatch.setattr("smbclient.listdir", fake_listdir)
    monkeypatch.setattr("smbclient.reset_connection_cache", fake_reset_connection_cache)

    scanner = SmbScanner()
    credential = ScanCredential(username="administrator", password="s3cret")
    outcome = await scanner.probe(
        "fileserver.example.com", port=445, timeout_seconds=5, credential=credential
    )

    assert outcome.status == DiscoveryResultStatus.UNREACHABLE
    assert outcome.error_message == "[Errno 104] Connection reset by peer"


async def test_probe_against_a_closed_local_port_is_unreachable() -> None:
    """No mocking: ``localhost:1`` refuses the connection for real.
    This is the regression case that caught the ``except ValueError``
    gap this test file's own authoring fixed in ``smb_scanner.py``.
    """
    scanner = SmbScanner()
    credential = ScanCredential(username="administrator", password="s3cret")
    outcome = await scanner.probe("127.0.0.1", port=1, timeout_seconds=5, credential=credential)

    assert outcome.status == DiscoveryResultStatus.UNREACHABLE
    assert outcome.error_message is not None


__all__: list[str] = []
