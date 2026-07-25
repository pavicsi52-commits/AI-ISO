"""Tests for :mod:`app.scanners.winrm_scanner`.

**Mocked, and here's why**: WinRM targets a *remote* Windows host with
its WinRM listener enabled (disabled by default even on Windows) --
there is no such host reachable in this environment, and this file
does not stand one up on the local development machine itself (see
``winrm_scanner.py``'s own module docstring for why). Every
success/auth-failed/transport-error test below patches
``winrm.protocol.Protocol.open_shell``/``close_shell`` -- the exact
boundary the scanner itself calls -- with the real
``winrm.exceptions`` types the library actually raises (confirmed by
reading ``winrm/transport.py`` directly), so what's under test is the
scanner's own request construction (a real, unpatched ``Protocol`` is
still built from the scanner's arguments) and its response/error
classification, not a re-implementation of pywinrm's own transport.

The one exception is ``test_probe_against_a_closed_local_port_is_
unreachable``, which makes no mock at all: a closed TCP port on
``localhost`` is real, verifiable local behavior. It also guards
against a regression this test file's own authoring caught live: a
refused connection surfaces from ``pywinrm`` as a bare
``requests.exceptions.ConnectionError`` (a real ``OSError`` subclass)
raised *before* any HTTP response exists, not as a
``winrm.exceptions.WinRMTransportError`` -- ``winrm_scanner.py`` now
has an explicit ``except OSError`` clause for exactly this.
"""

from __future__ import annotations

import pytest
from winrm.exceptions import InvalidCredentialsError, WinRMError, WinRMTransportError
from winrm.protocol import Protocol

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ScanCredential
from app.scanners.winrm_scanner import WinRmScanner

_REAL_SHELL_ID = "67A74EB8-6D70-4F19-9020-C0F1F86FCE68"


async def test_probe_without_a_username_fails_before_any_network_call() -> None:
    scanner = WinRmScanner()
    outcome = await scanner.probe("127.0.0.1", port=5985, timeout_seconds=5, credential=None)

    assert outcome.status == DiscoveryResultStatus.FAILURE
    assert outcome.error_message == "WinRM requires a credential with a username."


async def test_probe_reports_the_scanners_declared_protocol() -> None:
    assert WinRmScanner().protocol == ProtocolType.WINRM


async def test_probe_opens_and_closes_a_real_shell_id_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful probe must open a shell, report ``shell_opened``,
    and close the *same* shell id it opened -- this exercises the
    scanner's own real request-building (a genuine ``Protocol`` is
    constructed from the address/port/credential) end to end, only the
    two network-performing methods are replaced.
    """
    close_calls: list[str] = []

    def fake_open_shell(self: Protocol, *args: object, **kwargs: object) -> str:
        assert self.username == "administrator"
        return _REAL_SHELL_ID

    def fake_close_shell(self: Protocol, shell_id: str, close_session: bool = True) -> None:
        close_calls.append(shell_id)

    monkeypatch.setattr(Protocol, "open_shell", fake_open_shell)
    monkeypatch.setattr(Protocol, "close_shell", fake_close_shell)

    scanner = WinRmScanner()
    credential = ScanCredential(username="administrator", password="s3cret")
    outcome = await scanner.probe("127.0.0.1", port=5985, timeout_seconds=5, credential=credential)

    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.identity == {"shell_opened": True}
    assert outcome.latency_ms is not None
    assert outcome.latency_ms >= 0
    assert close_calls == [_REAL_SHELL_ID]


async def test_probe_uses_the_default_port_when_none_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_endpoints: list[str] = []

    def fake_open_shell(self: Protocol, *args: object, **kwargs: object) -> str:
        seen_endpoints.append(self.transport.endpoint)
        return _REAL_SHELL_ID

    def fake_close_shell(self: Protocol, shell_id: str, close_session: bool = True) -> None:
        pass

    monkeypatch.setattr(Protocol, "open_shell", fake_open_shell)
    monkeypatch.setattr(Protocol, "close_shell", fake_close_shell)

    scanner = WinRmScanner()
    credential = ScanCredential(username="administrator", password="s3cret")
    outcome = await scanner.probe("10.0.0.5", port=None, timeout_seconds=5, credential=credential)

    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert seen_endpoints == ["http://10.0.0.5:5985/wsman"]


async def test_probe_classifies_invalid_credentials_as_auth_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real message pywinrm's own transport layer raises on an
    HTTP 401 (see ``winrm/transport.py::_send_message_request``).
    """

    def fake_open_shell(self: Protocol, *args: object, **kwargs: object) -> str:
        raise InvalidCredentialsError("the specified credentials were rejected by the server")

    monkeypatch.setattr(Protocol, "open_shell", fake_open_shell)

    scanner = WinRmScanner()
    credential = ScanCredential(username="administrator", password="wrong")
    outcome = await scanner.probe("127.0.0.1", port=5985, timeout_seconds=5, credential=credential)

    assert outcome.status == DiscoveryResultStatus.AUTH_FAILED
    assert outcome.error_message == "the specified credentials were rejected by the server"


async def test_probe_classifies_a_transport_error_as_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``WinRMTransportError(protocol, code, response_text)`` -- the
    real 3-argument shape ``winrm/transport.py`` constructs it with for
    a non-2xx HTTP response other than 401.
    """

    def fake_open_shell(self: Protocol, *args: object, **kwargs: object) -> str:
        raise WinRMTransportError("http", 500, "<s:Fault>internal error</s:Fault>")

    monkeypatch.setattr(Protocol, "open_shell", fake_open_shell)

    scanner = WinRmScanner()
    credential = ScanCredential(username="administrator", password="s3cret")
    outcome = await scanner.probe("127.0.0.1", port=5985, timeout_seconds=5, credential=credential)

    assert outcome.status == DiscoveryResultStatus.UNREACHABLE
    assert outcome.error_message == "Bad HTTP response returned from server. Code 500"


async def test_probe_classifies_a_generic_winrm_error_as_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_open_shell(self: Protocol, *args: object, **kwargs: object) -> str:
        raise WinRMError("shell creation was refused by the remote shell resource")

    monkeypatch.setattr(Protocol, "open_shell", fake_open_shell)

    scanner = WinRmScanner()
    credential = ScanCredential(username="administrator", password="s3cret")
    outcome = await scanner.probe("127.0.0.1", port=5985, timeout_seconds=5, credential=credential)

    assert outcome.status == DiscoveryResultStatus.FAILURE
    assert outcome.error_message == "shell creation was refused by the remote shell resource"


async def test_probe_against_a_closed_local_port_is_unreachable() -> None:
    """No mocking: ``localhost:1`` refuses the connection for real.
    This is the regression case that caught the ``except OSError``
    gap this test file's own authoring fixed in ``winrm_scanner.py``.
    """
    scanner = WinRmScanner()
    credential = ScanCredential(username="administrator", password="s3cret")
    outcome = await scanner.probe("127.0.0.1", port=1, timeout_seconds=5, credential=credential)

    assert outcome.status == DiscoveryResultStatus.UNREACHABLE
    assert outcome.error_message is not None


__all__: list[str] = []
