"""Tests for :class:`app.scanners.sftp_scanner.SftpScanner` against the
same real ``openssh-server`` container ``tests/test_scanner_ssh.py``
uses (see ``tests/conftest.py``'s own module docstring).
"""

from __future__ import annotations

from app.models.enums import DiscoveryResultStatus
from app.scanners.base import ScanCredential
from app.scanners.sftp_scanner import SftpScanner
from tests.conftest import SSH_TEST_HOST, SSH_TEST_PASSWORD, SSH_TEST_PORT, SSH_TEST_USERNAME


async def test_probe_without_credential_fails() -> None:
    scanner = SftpScanner()
    outcome = await scanner.probe(
        SSH_TEST_HOST, port=SSH_TEST_PORT, timeout_seconds=5, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.FAILURE
    assert outcome.error_message is not None


async def test_probe_succeeds_and_lists_directory() -> None:
    scanner = SftpScanner()
    credential = ScanCredential(username=SSH_TEST_USERNAME, password=SSH_TEST_PASSWORD)
    outcome = await scanner.probe(
        SSH_TEST_HOST, port=SSH_TEST_PORT, timeout_seconds=5, credential=credential
    )
    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.identity["entry_count"] >= 0
    assert "SSH" in str(outcome.identity["server_version"])


async def test_probe_reports_auth_failed_for_wrong_password() -> None:
    scanner = SftpScanner()
    credential = ScanCredential(username=SSH_TEST_USERNAME, password="definitely-wrong")
    outcome = await scanner.probe(
        SSH_TEST_HOST, port=SSH_TEST_PORT, timeout_seconds=5, credential=credential
    )
    assert outcome.status == DiscoveryResultStatus.AUTH_FAILED


async def test_probe_credential_without_username_fails() -> None:
    scanner = SftpScanner()
    credential = ScanCredential(username=None, password=SSH_TEST_PASSWORD)
    outcome = await scanner.probe(
        SSH_TEST_HOST, port=SSH_TEST_PORT, timeout_seconds=5, credential=credential
    )
    assert outcome.status == DiscoveryResultStatus.FAILURE


async def test_probe_unreachable_returns_unreachable_or_timeout() -> None:
    scanner = SftpScanner()
    credential = ScanCredential(username=SSH_TEST_USERNAME, password=SSH_TEST_PASSWORD)
    outcome = await scanner.probe(SSH_TEST_HOST, port=1, timeout_seconds=1, credential=credential)
    assert outcome.status in (
        DiscoveryResultStatus.UNREACHABLE,
        DiscoveryResultStatus.TIMEOUT,
    )
