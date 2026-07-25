"""Tests for :mod:`app.scanners.wmi_scanner`.

Unlike every other file in this test batch, WMI is genuinely,
live-verifiable *here*: WMI is Windows-only, and this development
machine itself is Windows (see ``wmi_scanner.py``'s own module
docstring). Every success-path test below runs a real WMI query
(``Win32_OperatingSystem``) against this machine's own local WMI
provider via ``computer="localhost"`` -- no mocking. The two failure
paths use real, naturally-occurring WMI failures too (a nonexistent
remote host, and the real ``x_wmi`` COM error Windows itself raises
when explicit credentials are supplied for a local connection) rather
than synthesizing them, since both are genuinely reproducible on this
machine without needing a second real host.
"""

from __future__ import annotations

import time

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ScanCredential
from app.scanners.wmi_scanner import WmiScanner


async def test_probe_succeeds_against_local_wmi_provider() -> None:
    """A real, unauthenticated local WMI query must succeed and report
    genuine ``Win32_OperatingSystem`` fields for this machine.
    """
    scanner = WmiScanner()
    outcome = await scanner.probe("localhost", port=None, timeout_seconds=15, credential=None)

    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.error_message is None
    assert outcome.latency_ms is not None
    assert outcome.latency_ms >= 0
    assert isinstance(outcome.identity["caption"], str)
    assert "Windows" in outcome.identity["caption"]
    assert isinstance(outcome.identity["version"], str)
    assert isinstance(outcome.identity["build_number"], str)
    assert isinstance(outcome.identity["architecture"], str)


async def test_probe_reports_the_scanners_declared_protocol() -> None:
    assert WmiScanner().protocol == ProtocolType.WMI


async def test_probe_without_a_credential_still_succeeds_locally() -> None:
    """No credential at all is the common case for a local/agent-based
    probe -- ``wmi.WMI(computer=...)`` with no ``user``/``password``
    kwargs uses the calling process's own security context.
    """
    scanner = WmiScanner()
    outcome = await scanner.probe(
        "localhost", port=None, timeout_seconds=15, credential=ScanCredential()
    )

    assert outcome.status == DiscoveryResultStatus.SUCCESS


async def test_probe_reports_real_latency_less_than_the_full_timeout_budget() -> None:
    scanner = WmiScanner()
    start = time.perf_counter()
    outcome = await scanner.probe("localhost", port=None, timeout_seconds=15, credential=None)
    wall_ms = (time.perf_counter() - start) * 1000

    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.latency_ms is not None
    assert outcome.latency_ms <= wall_ms + 50  # small allowance for executor scheduling


async def test_probe_with_explicit_credentials_against_a_local_target_is_rejected() -> None:
    """Windows' own WMI/DCOM stack genuinely refuses explicit
    credentials for a *local* connection ("User credentials cannot be
    used for local connections") -- this is real Windows behavior, not
    a simulated failure, and it does not contain "access"/"denied", so
    the scanner's own classification logic must fall through to
    ``UNREACHABLE`` rather than ``AUTH_FAILED``.
    """
    scanner = WmiScanner()
    credential = ScanCredential(username="nonexistent-user-12345", password="wrong-password")
    outcome = await scanner.probe("localhost", port=None, timeout_seconds=15, credential=credential)

    assert outcome.status == DiscoveryResultStatus.UNREACHABLE
    assert outcome.error_message is not None
    assert "credentials cannot be used for local connections" in outcome.error_message.lower()


async def test_probe_against_an_unreachable_host_reports_unreachable() -> None:
    """A hostname that cannot be resolved/reached over RPC is a real,
    naturally-occurring WMI failure -- no real second host is needed to
    prove this path, unlike the remote-only scanners in this batch.
    """
    scanner = WmiScanner()
    outcome = await scanner.probe(
        "nonexistent-host-xyz-12345.invalid",
        port=None,
        timeout_seconds=10,
        credential=None,
    )

    assert outcome.status == DiscoveryResultStatus.UNREACHABLE
    assert outcome.error_message is not None


__all__: list[str] = []
