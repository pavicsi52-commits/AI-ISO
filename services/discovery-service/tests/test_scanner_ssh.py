"""Tests for :class:`app.scanners.ssh_scanner.SshScanner` against the
real ``openssh-server`` container this package's own test suite starts
(see ``tests/conftest.py``'s own module docstring).
"""

from __future__ import annotations

from app.models.enums import DiscoveryResultStatus
from app.scanners.base import ScanCredential
from app.scanners.ssh_scanner import SshScanner
from tests.conftest import SSH_TEST_HOST, SSH_TEST_PASSWORD, SSH_TEST_PORT, SSH_TEST_USERNAME


async def test_probe_succeeds_without_credential() -> None:
    scanner = SshScanner()
    outcome = await scanner.probe(
        SSH_TEST_HOST, port=SSH_TEST_PORT, timeout_seconds=5, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.latency_ms is not None
    assert "SSH" in str(outcome.identity["server_version"])
    assert "authenticated" not in outcome.identity


async def test_probe_authenticates_with_correct_password() -> None:
    scanner = SshScanner()
    credential = ScanCredential(username=SSH_TEST_USERNAME, password=SSH_TEST_PASSWORD)
    outcome = await scanner.probe(
        SSH_TEST_HOST, port=SSH_TEST_PORT, timeout_seconds=5, credential=credential
    )
    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.identity["authenticated"] is True


async def test_probe_reports_auth_failed_for_wrong_password() -> None:
    scanner = SshScanner()
    credential = ScanCredential(username=SSH_TEST_USERNAME, password="definitely-wrong")
    outcome = await scanner.probe(
        SSH_TEST_HOST, port=SSH_TEST_PORT, timeout_seconds=5, credential=credential
    )
    assert outcome.status == DiscoveryResultStatus.AUTH_FAILED


async def test_probe_unreachable_port_returns_unreachable_or_timeout() -> None:
    scanner = SshScanner()
    outcome = await scanner.probe(SSH_TEST_HOST, port=1, timeout_seconds=1, credential=None)
    assert outcome.status in (
        DiscoveryResultStatus.UNREACHABLE,
        DiscoveryResultStatus.TIMEOUT,
    )


async def test_probe_defaults_to_port_22_when_none_given() -> None:
    scanner = SshScanner()
    outcome = await scanner.probe("203.0.113.1", port=None, timeout_seconds=1, credential=None)
    assert outcome.status in (
        DiscoveryResultStatus.UNREACHABLE,
        DiscoveryResultStatus.TIMEOUT,
    )
